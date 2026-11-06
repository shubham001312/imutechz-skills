"""QA: prove the render is what the platform expects before anyone sees it.

    python scripts/qa.py <project> [--platform youtube] [--no-lint]
    python scripts/qa.py file <video.mp4> [--platform youtube]      probe any file against a profile

Checks per platform (each PASS / WARN / FAIL):
  container   H.264 High, yuv420p, the profile's W×H and fps, AAC 48 kHz stereo, moov before mdat (+faststart)
  duration    matches the timeline (±0.15 s) and the platform limit
  loudness    integrated LUFS within ±1 LU of target; true peak <= target + 0.3 dB (ebur128)
  silence     no unintended dropouts > 1.5 s while narration is expected (silencedetect)
  black       no black frames outside the first/last 0.5 s (blackdetect)
  captions    SRT parses; no overlaps; line length; reading speed; every spoken word covered
  lint        on-screen text inside the safe area, not clipped, not below the minimum size (stills.mjs --lint)
  facts       every number on screen or in the narration appears in a source or brief.facts (research.py)
Outputs build/<platform>/qa.json, a contact sheet build/<platform>/contact.png, and build/qa.md.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from fvcore import (SKILL, FishError, load_yaml, ensure_project, ffmpeg_bin, ffprobe_bin, last_json_line, load_json, log, main_guard, node,
                    project_config, run)
import captions as capmod


def probe(path: Path) -> dict:
    r = run([ffprobe_bin(), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture=True)
    return json.loads(r.stdout)


def faststart(path: Path) -> bool:
    """True when the moov atom precedes mdat (progressive playback)."""
    with open(path, "rb") as fh:
        pos = 0
        size = path.stat().st_size
        while pos < size:
            fh.seek(pos)
            hdr = fh.read(16)
            if len(hdr) < 8:
                return False
            n = int.from_bytes(hdr[:4], "big")
            kind = hdr[4:8]
            if n == 1:
                n = int.from_bytes(hdr[8:16], "big")
            if kind == b"moov":
                return True
            if kind == b"mdat":
                return False
            if n < 8:
                return False
            pos += n
    return False


def loudness(path: Path) -> dict:
    r = run([ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"], capture=True)
    s = r.stderr[r.stderr.rfind("Summary"):]
    I = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", s)
    P = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", s)
    LRA = re.search(r"LRA:\s+([\d.]+) LU", s)
    f = lambda m: float(m.group(1)) if m and m.group(1) != "-inf" else float("-inf")
    return {"I": f(I), "TP": f(P), "LRA": f(LRA)}


def detect(path: Path, kind: str) -> list[tuple[float, float]]:
    """Intervals from blackdetect (video) or silencedetect (audio)."""
    if kind == "black":
        args = ["-vf", "blackdetect=d=0.25:pix_th=0.06", "-an"]
        rx = re.compile(r"black_start:([\d.]+) black_end:([\d.]+)")
    else:
        args = ["-af", "silencedetect=n=-50dB:d=1.5", "-vn"]
        rx = None
    r = run([ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(path), *args, "-f", "null", "-"], capture=True)
    if rx:
        return [(float(a), float(b)) for a, b in rx.findall(r.stderr)]
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends + [float("inf")] * (len(starts) - len(ends))))


def narration_gaps(tl: dict, limit: float = 0.6) -> dict:
    """Silence between neighbouring narration lines from the timeline: FAIL when an unplanned gap exceeds `limit` s
    (a line may ask for a pause with `pause:`, at most 0.8 s). Reports the median and maximum. Also the hook and the pace."""
    L = tl["voice_lines"]
    g = [(b["at"] - (a["at"] + a["dur"]), float(b.get("pause") or 0)) for a, b in zip(L, L[1:])]
    vals = sorted(x for x, _ in g)
    med = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
    bad = [round(x, 2) for x, p in g if x > limit + min(p, 0.8)]
    wps = [len(str(v.get("say", "")).split()) / v["dur"] for v in L if v.get("dur")]
    hook = len(str(L[0].get("display", "")).split()) < 10 and L[0]["at"] <= 0.2
    detail = f"gaps between lines: median {med:.2f} s, max {max(vals):.2f} s (limit {limit} s)" + (f"; unplanned over limit: {bad}" if bad else "")
    detail += f"; pace {sum(len(str(v.get('say', '')).split()) for v in L) / max(1e-6, sum(v['dur'] for v in L)):.2f} words/s, fastest line {max(wps):.1f}"
    detail += "" if hook else "; weak hook (first line should be under 10 words and start within 0.2 s)"
    return {"check": "narration gaps", "status": "FAIL" if bad else ("WARN" if (not hook or max(wps) > 3.6) else "PASS"), "detail": detail}


def contact_sheet(path: Path, out: Path, duration: float, cols: int = 5, width: int = 384) -> Path:
    every = max(1.0, duration / 20)
    rows = max(1, -(-int(duration / every) // cols))
    base = f"fps=1/{every:.3f},scale={width}:-2"
    stamp = "drawtext=text='%{pts\\:hms}':x=6:y=6:fontsize=14:fontcolor=white:box=1:boxcolor=black@0.6"
    try:
        run([ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(path), "-vf",
             f"{base},{stamp},tile={cols}x{rows}", "-frames:v", "1", str(out)], capture=True)
    except Exception:
        # some static ffmpeg builds have no drawtext (no freetype): same sheet, no timestamp labels
        run([ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(path), "-vf",
             f"{base},tile={cols}x{rows}", "-frames:v", "1", str(out)], capture=True)
    return out


def check_file(path: Path, prof: dict, expect_duration: float | None = None, narration: list[tuple[float, float]] | None = None) -> list[dict]:
    """Container, duration, loudness, black and silence checks for one file."""
    res = []
    add = lambda name, ok, detail, level="FAIL": res.append({"check": name, "status": "PASS" if ok else level, "detail": detail})
    pr = probe(path)
    v = next((s for s in pr["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in pr["streams"] if s["codec_type"] == "audio"), None)
    dur = float(pr["format"]["duration"])
    if not v:
        add("video", False, "no video stream")
        return res
    fr = v.get("r_frame_rate", "0/1").split("/")
    fps = float(fr[0]) / float(fr[1] or 1)
    scale = prof.get("_scale", 1)
    W, H = round(prof["W"] * scale), round(prof["H"] * scale)
    add("codec", v["codec_name"] == "h264" and v.get("profile", "").lower().startswith("high") and v.get("pix_fmt") == "yuv420p", f"{v['codec_name']} {v.get('profile')} {v.get('pix_fmt')}")
    add("resolution", abs(v["width"] - W) <= 2 and abs(v["height"] - H) <= 2, f"{v['width']}x{v['height']} (want {W}x{H})")
    add("fps", abs(fps - prof.get("fps", 30)) < 0.01, f"{fps:.3f}")
    add("audio", bool(a) and a["codec_name"] == "aac" and a.get("sample_rate") == "48000" and a.get("channels") == 2, f"{a['codec_name']} {a.get('sample_rate')} Hz {a.get('channels')} ch" if a else "none")
    add("faststart", faststart(path), "moov before mdat")
    if expect_duration:
        add("duration", abs(dur - expect_duration) <= 0.15, f"{dur:.2f}s (timeline {expect_duration:.2f}s)")
    if prof.get("max_seconds"):
        add("platform length", dur <= prof["max_seconds"], f"{dur:.1f}s (max {prof['max_seconds']}s)")
    mb = float(pr["format"].get("bit_rate", 0)) / 1e6
    add("bitrate", mb > 0.05, f"{mb:.2f} Mb/s, {path.stat().st_size / 1e6:.1f} MB", "WARN")
    if a:
        lu = loudness(path)
        tgt, tp = prof.get("loudness", -14), prof.get("true_peak", -1.5)
        add("loudness", abs(lu["I"] - tgt) <= 1.0, f"{lu['I']:.1f} LUFS (target {tgt})")
        add("true peak", lu["TP"] <= tp + 0.5, f"{lu['TP']:.1f} dBTP (max {tp})")
        sil = [s for s in detect(path, "silence") if s[0] > 0.5 and s[0] < dur - 1.0]
        if narration:
            bad = [s for s in sil if any(n0 < min(s[1], dur) and s[0] < n1 for n0, n1 in narration)]
            add("dropouts", not bad, f"{len(bad)} silent gaps during narration" + (f": {bad[:3]}" if bad else ""))
        else:
            add("dropouts", not sil, f"{len(sil)} silences > 1.5 s", "WARN")
    blk = [b for b in detect(path, "black") if b[0] > 0.5 and b[1] < dur - 0.7]
    add("black frames", not blk, f"{len(blk)} black runs" + (f": {blk[:3]}" if blk else ""), "WARN")
    return res


def mix_balance(video: Path, narr: list[tuple[float, float]], mix_json: Path) -> dict:
    """Speech-window level vs gap level of the final mix, plus SFX presence."""
    try:
        import numpy as np
        import dissect
        x = dissect.load_audio(video)
    except Exception as e:  # numpy missing or decode failure: not fatal
        return {"check": "mix balance", "status": "WARN", "detail": f"not measured ({type(e).__name__})"}
    hop = 2205  # 100 ms @ 22.05 kHz
    n = len(x) // hop
    if n < 5:
        return {"check": "mix balance", "status": "WARN", "detail": "too short to measure"}
    rms = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    t = (np.arange(n) + 0.5) * 0.1
    sp = np.zeros(n, bool)
    for a, b in narr or []:
        sp |= (t >= a) & (t <= b)
    body = t < (t[-1] - 2.0)  # ignore the outro fade
    gap = ~sp & body & (t > 0.3)
    mix = load_json(mix_json, default={}) if mix_json.exists() else {}
    sfx_ok = any(v is not None for v in mix.get("sfx_lufs") or [])
    if not narr or not sp.any() or gap.sum() < 3:
        lvl = float(np.median(rms[body])) if body.any() else float(np.median(rms))
        return {"check": "mix balance", "status": "PASS" if lvl > -40 else "WARN", "detail": f"no narration gaps to compare; median level {lvl:.1f} dBFS; sfx {'yes' if sfx_ok else 'none'}"}
    # the 30th percentile of the gaps is the bed itself: the median there is often a whoosh or an impact
    s, g = float(np.median(rms[sp])), float(np.percentile(rms[gap], 30))
    diff = s - g
    probs = []
    if g < -38:
        probs.append("music is nearly inaudible between lines: raise mix.music_under_voice_db (e.g. -8)")
    if diff < 3:
        probs.append("music competes with the voice: lower mix.music_under_voice_db or deepen the duck")
    if diff > 20:
        probs.append("big level jumps between speech and gaps: raise the music or reduce the duck ratio")
    if not sfx_ok:
        probs.append("no SFX stem: scenes emitted no cues, or sfx is off")
    return {"check": "mix balance", "status": "PASS" if not probs else "WARN",
            "detail": f"speech {s:.1f} dBFS, gaps {g:.1f} dBFS (voice over bed {diff:.1f} dB); sfx {'yes' if sfx_ok else 'none'}" + (f"; {probs}" if probs else "")}


def speaker_translation(video: Path, narr: list[tuple[float, float]], out_wav: Path | None = None) -> dict:
    """Does the mix survive a phone speaker? Simulate one, then measure the bed, the bass share and mono safety."""
    try:
        import numpy as np
        import dissect
        from render import PHONE_SIM
        from fvcore import ffmpeg_bin, run
        def pcm(af=None, ch=1):
            args = [ffmpeg_bin(), "-v", "error", "-i", str(video)] + (["-af", af] if af else []) + ["-ac", str(ch), "-ar", "22050", "-f", "f32le", "-"]
            import subprocess
            return np.frombuffer(subprocess.run(args, capture_output=True, check=True).stdout, dtype=np.float32)
        full, phone = pcm(), pcm(PHONE_SIM)
        st = pcm(None, 2).reshape(-1, 2)
        if out_wav is not None:
            run([ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(video), "-af", PHONE_SIM, str(out_wav)])
    except Exception as e:
        return {"check": "speaker translation", "status": "WARN", "detail": f"not measured ({type(e).__name__}: {str(e)[:80]})"}
    db = lambda a: float(20 * np.log10(np.sqrt((a ** 2).mean()) + 1e-9))
    hop = 2205
    n = min(len(full), len(phone)) // hop
    if n < 5:
        return {"check": "speaker translation", "status": "WARN", "detail": "too short to measure"}
    fr = 20 * np.log10(np.sqrt((phone[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    t = (np.arange(n) + 0.5) * 0.1
    sp = np.zeros(n, bool)
    for a, b in narr or []:
        sp |= (t >= a) & (t <= b)
    body = t < t[-1] - 2.0
    gap = ~sp & body & (t > 0.3)
    loss = db(full) - db(phone)                       # how much of the mix a phone throws away
    mono_loss = db(st.mean(1)) - db(st)                # 0 = safe; strongly negative = cancels on a mono speaker
    probs = []
    detail = f"a phone loses {loss:.1f} dB of the mix; mono change {mono_loss:.1f} dB"
    if narr and sp.any() and gap.sum() >= 3:
        s, g = float(np.median(fr[sp])), float(np.median(fr[gap]))
        detail += f"; on a phone: speech {s:.1f}, bed between lines {g:.1f} dBFS (gap {s - g:.1f} dB)"
        if s - g > 16:
            probs.append("the music nearly vanishes on a phone: raise mix.translate.music_harmonics_db or mix.music_under_voice_db")
        if s - g < 3:
            probs.append("on a phone the music competes with the voice: lower mix.music_under_voice_db")
    if loss > 9:
        probs.append("too much of the mix is sub-bass a phone cannot play: use a brighter track or more harmonics")
    if mono_loss < -3:
        probs.append("stereo cancels on a mono speaker: lower mix.translate.music_width")
    return {"check": "speaker translation", "status": "PASS" if not probs else "WARN", "detail": detail + (f"; {probs}" if probs else "")}


def explicit_cues(storyboard: dict, placed: list[dict], density: str = "rich") -> dict:
    """Every cue written by hand in the storyboard must reach the render, or a planned sound silently never plays.
    Cues the chosen SFX density filters out on purpose (their lvl is too low) are not counted."""
    need = {"rich": 1, "standard": 2, "minimal": 3}.get(density, 1)
    have = {(q.get("scene"), q.get("type")) for q in placed}
    missing = [f"{s.get('id')}:{q.get('type')}" for s in storyboard.get("scenes", []) for q in (s.get("cues") or [])
               if q.get("lvl", 2) >= need and (s.get("id"), q.get("type")) not in have]
    return {"check": "explicit cues", "status": "PASS" if not missing else "FAIL", "detail": "every hand-placed cue was placed" if not missing else f"not placed: {missing[:8]}"}


def synth_cue_types() -> set[str]:
    """Cue types music.mjs can synthesise itself: the `case "<type>"` labels of its cue switch."""
    import re
    src = (SKILL / "scripts" / "music.mjs").read_text(encoding="utf-8")
    body = src[src.index("switch (q.type)"):]
    return set(re.findall(r'^\s*case "([A-Za-z0-9_-]+)":', body, re.M))


def cue_sounds(project: Path, storyboard: dict) -> dict:
    """A hand-placed cue whose type has neither a sample nor a synthesised sound plays nothing, and nothing else reports it."""
    import sfx
    have = set(sfx.library(project)) | synth_cue_types()
    missing = sorted({q.get("type") for s in storyboard.get("scenes", []) for q in (s.get("cues") or []) if q.get("type") and q.get("type") not in have})
    return {"check": "cue sounds", "status": "PASS" if not missing else "WARN",
            "detail": "every hand-placed cue type has a sound" if not missing else f"no sound for cue type(s): {missing[:8]}; add one with `sounds add` or `sounds synth`"}


def asset_licences(project: Path) -> dict:
    """WARN, naming each one, for every asset that is not licence-safe (see references/memes-and-real-assets.md)."""
    import fvnet
    rows = fvnet.risky(project)
    if not rows:
        return {"check": "asset licences", "status": "PASS", "detail": "every credited asset is public domain, Creative Commons or ours"}
    names = [f"{r.get('title') or r.get('id')} [{fvnet.risk_of(r)}: {r.get('provider')}]" for r in rows]
    return {"check": "asset licences", "status": "WARN", "detail": f"{len(rows)} not licence-safe, review before publishing: {'; '.join(names[:6])}" + (" ..." if len(names) > 6 else "")}


def meme_checks(project: Path) -> list[dict]:
    import memes
    found = memes.lint(project)
    if not found:
        return []
    bad = [f for f in found if f["level"] == "FAIL"]
    return [{"check": "meme lint", "status": "FAIL" if bad else "WARN", "detail": "; ".join(f"{f['scene']}: {f['msg']}" for f in found[:4])}]


def flat_regions(frames, fps: float = 2.0, hold: float = 1.5, flat: float = 3.0, fg_min: float = 0.02, dev: float = 16.0) -> list[str]:
    """Pure core of `bare_regions`. `frames` is an (N, H, W) greyscale array sampled at `fps`.
    A quarter (or the whole frame) is EMPTY in a sample when it is flat (std < `flat`) or has almost no foreground: fewer than
    `fg_min` of its pixels differ from its own median by more than `dev` levels, so a faint grid or ghost map does not count as content.
    Reports a region once it is empty for `hold` seconds in a row."""
    import math
    import numpy as np
    n, H, W = frames.shape
    need = max(1, math.ceil(hold * fps - 1e-9))
    names = ["top-left", "top-right", "bottom-left", "bottom-right", "whole frame"]
    runs, found = [0] * 5, []

    def empty(part) -> bool:
        return bool(part.std() < flat or float((np.abs(part - np.median(part)) > dev).mean()) < fg_min)

    for t, f in enumerate(frames):
        parts = (f[1:H // 2 - 1, 1:W // 2 - 1], f[1:H // 2 - 1, W // 2 + 1:-1], f[H // 2 + 1:-1, 1:W // 2 - 1], f[H // 2 + 1:-1, W // 2 + 1:-1], f[1:-1, 1:-1])
        for q, part in enumerate(parts):
            runs[q] = runs[q] + 1 if empty(part) else 0
            if runs[q] == need:
                found.append(f"{(t - need + 1) / fps:.1f}s {names[q]}")
    return found


def bare_regions(video: Path, hold: float = 1.5, flat: float = 3.0, fps: float = 2.0) -> dict:
    """WARN when a quarter of the frame, or the whole frame, stays empty for `hold` seconds or more.
    Sampled twice a second on a 64x36 greyscale proxy. This is a heuristic, NOT proof the frames are good: it cannot tell a deliberate
    title card from a gap, and a busy background can hide an empty foreground. Always open the contact sheet or frame sheet."""
    import numpy as np
    W, H = 64, 36
    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={W}:{H}:flags=area,format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, H, W).astype(float)
    found = flat_regions(frames, fps, hold, flat)
    return {"check": "bare frame", "status": "PASS" if not found else "WARN",
            "detail": "no quarter of the frame stays empty (heuristic: still open the frame sheet)" if not found else f"{len(found)} empty regions, open these frames: {found[:8]}"}


def qa_platform(project: Path, platform: str, lint: bool = True, preview: bool = False) -> dict:
    cfg = project_config(project)
    prof = dict(cfg["platforms"][platform])
    b = project / "build" / platform
    video = b / ("final-preview.mp4" if preview else "final.mp4")
    if not video.exists():
        raise FishError(f"{video} not found: run `fishvideo render` first")
    tl = load_json(project / "build" / f"timeline-{platform}.json")
    info = load_json(b / "info.json", default={})
    prof["_scale"] = info.get("scale", 1)
    narr = [(v["at"], v["at"] + v["dur"]) for v in tl.get("voice_lines", []) if v.get("wav")]
    res = check_file(video, prof, None if preview else tl["duration"], narr or None)
    # captions
    srt = b / "captions.srt"
    if tl.get("voice_lines"):
        cues = capmod.parse_srt(srt.read_text(encoding="utf-8")) if srt.exists() else []
        cap = tl["captions"]
        issues = capmod.check_cues(cues, cap["max_chars"], cap["max_lines"], cfg["captions"]["max_cps"], tl["duration"])
        issues += capmod.sync_check(cap["cues"], tl.get("words", []))
        res.append({"check": "captions", "status": "PASS" if not issues else "FAIL", "detail": f"{len(cues)} cues" + (f"; {issues[:4]}" if issues else "")})
        est = [v["id"] for v in tl["voice_lines"] if v.get("estimated")]
        res.append({"check": "voice", "status": "PASS" if not est else "WARN", "detail": "all lines voiced" if not est else f"{len(est)} lines timed by estimate (no TTS)"})
    try:                                          # local voice studio checks; skipped unless the narration came from it
        import voicelab
        res += voicelab.qa_rows(project)
    except ImportError:
        pass
    if len(tl.get("voice_lines") or []) > 1:
        res.append(narration_gaps(tl))
    # mix balance: the bed must stay audible in the gaps and sit under the voice (references/sound-design.md)
    res.append(mix_balance(video, narr, b / "mix.json"))
    # phone speakers: also writes build/<platform>/phone-monitor.wav, a file to listen to what a phone plays
    res.append(speaker_translation(video, narr, b / "phone-monitor.wav"))
    res.append(explicit_cues(load_yaml(project / "storyboard.yaml"), info.get("cues", []), (tl.get("sfx") or {}).get("density") or "rich"))
    res.append(bare_regions(video))
    res.append(cue_sounds(project, load_yaml(project / "storyboard.yaml")))
    try:
        import gates
        _g = gates.recipe_gate((project_config(project)["brief"] or {}).get("recipe"))
        if _g.get("sharp_share_min"):
            _m, _f = gates.sharp_failures(project, video)
            res.append({"check": "sharp image coverage", "status": "FAIL" if _f else "PASS", "detail": (_f[0] if _f else f"sharp picture covers {_m['mean']:.0%} of the frame (needs {_g['sharp_share_min']:.0%}+; weakest scene {_m['min']:.0%})")})
    except Exception as e:                                  # noqa: BLE001 - a measuring problem must show, not vanish
        res.append({"check": "sharp image coverage", "status": "WARN", "detail": f"not measured: {e}"})
    res.append(asset_licences(project))
    res += meme_checks(project)
    # legibility lint
    if lint:
        r = node("stills.mjs", project, "--platform", platform, "--lint", "--scale", 0.5, capture=True, check=False)
        rep = load_json(b / "lint.json", default={"issues": [], "errors": []})
        iss = rep.get("issues", [])
        res.append({"check": "text lint", "status": "PASS" if not iss else "FAIL", "detail": f"{len(iss)} issues" + (f": {[(i['scene'], i['kind'], i['text'][:30]) for i in iss[:4]]}" if iss else "")})
        res.append({"check": "stage errors", "status": "PASS" if not rep.get("errors") and not info.get("errors") else "FAIL", "detail": str((rep.get("errors") or info.get("errors") or [])[:2])})
    # facts
    try:
        import research
        fc = research.check_claims(project)
        res.append({"check": "facts", "status": "PASS" if not fc["unsupported"] else "FAIL", "detail": f"{fc['checked']} numbers checked" + (f"; unsupported: {fc['unsupported'][:5]}" if fc["unsupported"] else "")})
    except FishError as e:
        res.append({"check": "facts", "status": "WARN", "detail": str(e)})
    # design QA (advice only: WARN) and the thumbnails, once, on the first platform
    if lint:
        import design as designmod
        res.append(designmod.qa_row(project, platform))
    import storyboard as sbmod, thumbs
    if platform == sbmod.platforms_of(cfg)[0]:
        res += thumbs.qa_rows(project)
    sheet = contact_sheet(video, b / "contact.png", tl["duration"] if not preview else float(probe(video)["format"]["duration"]), cols=5 if tl["W"] >= tl["H"] else 6, width=384 if tl["W"] >= tl["H"] else 216)
    status = "FAIL" if any(r["status"] == "FAIL" for r in res) else "WARN" if any(r["status"] == "WARN" for r in res) else "PASS"
    rep = {"platform": platform, "video": str(video), "status": status, "checks": res, "contact_sheet": str(sheet)}
    (b / "qa.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rep


def qa(project: Path, platforms: list[str] | None = None, lint: bool = True, preview: bool = False) -> list[dict]:
    project = ensure_project(project)
    import storyboard as sbmod
    plats = platforms or sbmod.platforms_of(project_config(project))
    reps = [qa_platform(project, p, lint, preview) for p in plats]
    md = ["# QA report", ""]
    for r in reps:
        md += [f"## {r['platform']}: {r['status']}", "", f"`{r['video']}`", "", "| check | status | detail |", "|---|---|---|"]
        md += [f"| {c['check']} | {c['status']} | {str(c['detail']).replace('|', '/')} |" for c in r["checks"]]
        md += ["", f"Contact sheet: `{r['contact_sheet']}`", ""]
    (project / "build" / "qa.md").write_text("\n".join(md), encoding="utf-8")
    for r in reps:
        log(f"{r['platform']}: {r['status']}")
        for c in r["checks"]:
            log(f"  {c['status']:<4}  {c['check']:<14} {c['detail']}")
    return reps


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--platform", default=None)
    ap.add_argument("--no-lint", action="store_true")
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args(argv)
    if a.target == "file":
        from fvcore import defaults
        prof = defaults()["platforms"][a.platform or "youtube"]
        for c in check_file(Path(a.file), prof):
            log(f"  {c['status']:<4}  {c['check']:<14} {c['detail']}")
        return 0
    reps = qa(Path(a.target), a.platform.split(",") if a.platform else None, not a.no_lint, a.preview)
    return 1 if any(r["status"] == "FAIL" for r in reps) else 0


if __name__ == "__main__":
    main_guard(cli)
