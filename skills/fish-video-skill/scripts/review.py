"""Self-review: contact sheets plus measured findings, so the agent looks before it ships.

    python scripts/review.py <project> [--platform shorts]

Writes build/<platform>/review/{sheet-beats,sheet-cuts,sheet-hook}.jpg and checks.json, and
<project>/REVIEW.md. Warnings are questions, not failures. Never score the film out of 10: a score
finds nothing to fix. Where numbers and eyes disagree, trust the numbers. The reviewer cannot hear:
audio is measured with commands (dissect.py), not judged.
"""
from __future__ import annotations

import argparse
import io
import re
import subprocess
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw
except ImportError as e:  # pragma: no cover
    raise SystemExit("review needs numpy and Pillow: pip install numpy pillow") from e

from fvcore import FishError, ensure_project, ffmpeg_bin, load_json, log, main_guard, project_config, save_json

PHONE_W = 360
AN_FPS = 10
AN_W = 180
SECTION = "## What I looked at (the agent fills this in)"
PLACEHOLDER = "(One sentence per beat frame naming every object, then the weakest shot. Read this before changing anything.)"
NOTE = ("Never score the film out of 10: a score finds nothing to fix. Where numbers and eyes disagree, trust the numbers. "
        "The reviewer cannot hear: audio is measured with commands.")


# ---------------------------------------------------------------- frames
def grab(video: Path, t: float, width: int = PHONE_W) -> Image.Image | None:
    r = subprocess.run([ffmpeg_bin(), "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
    if r.returncode or not r.stdout:
        return None
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")


def sheet(items: list[tuple[Image.Image | None, str]], out: Path, cols: int, tile_w: int, aspect: float) -> None:
    tile_h = int(tile_w * aspect)
    pad, lab = 6, 18
    rows = max(1, -(-len(items) // cols))
    S = Image.new("RGB", (cols * (tile_w + pad) + pad, rows * (tile_h + lab + pad) + pad), (20, 20, 24))
    d = ImageDraw.Draw(S)
    for i, (im, label) in enumerate(items):
        x = pad + (i % cols) * (tile_w + pad)
        y = pad + (i // cols) * (tile_h + lab + pad)
        d.text((x + 2, y + 3), label, fill=(240, 240, 240))
        if im is not None:
            S.paste(im.resize((tile_w, tile_h)), (x, y + lab))
        else:
            d.rectangle([x, y + lab, x + tile_w, y + lab + tile_h], outline=(120, 40, 40))
    out.parent.mkdir(parents=True, exist_ok=True)
    S.save(out, quality=82)


def _h(W: int, H: int) -> int:
    return max(2, int(round(AN_W * H / W / 2)) * 2)


def analysis_frames(video: Path, W: int, H: int) -> np.ndarray:
    h = _h(W, H)
    r = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(video), "-an", "-vf", f"fps={AN_FPS},scale={AN_W}:{h},format=gray",
                        "-f", "rawvideo", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.uint8)
    n = len(a) // (AN_W * h)
    return a[: n * AN_W * h].reshape(n, h, AN_W).astype(np.float32)


def first_frame(video: Path, W: int, H: int) -> np.ndarray | None:
    h = _h(W, H)
    r = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(video), "-frames:v", "1", "-an", "-vf", f"scale={AN_W}:{h},format=gray",
                        "-f", "rawvideo", "-"], capture_output=True)
    if len(r.stdout) < AN_W * h:
        return None
    return np.frombuffer(r.stdout, dtype=np.uint8)[: AN_W * h].reshape(h, AN_W).astype(np.float32)


def detail(g: np.ndarray) -> float:
    """Laplacian variance: edge/detail energy of a grayscale frame."""
    lap = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    return float(lap.var())


def runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            if j - i >= min_len:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


# ---------------------------------------------------------------- checks
def find(sev: str, t, where: str, problem: str, fix: str, check: str) -> dict:
    return {"sev": sev, "t": None if t is None else round(float(t), 2), "where": where, "problem": problem, "fix": fix, "check": check}


def run_checks(video: Path, tl: dict, cfg: dict, platform: str) -> tuple[dict, list[dict]]:
    W, H, dur = int(tl.get("W", 1080)), int(tl.get("H", 1920)), float(tl.get("duration") or 0)
    scenes, lines, words = tl.get("scenes", []), tl.get("voice_lines", []), tl.get("words", [])
    cues = (tl.get("captions") or {}).get("cues") or []
    brief = cfg.get("brief", {})
    shorts = platform == "shorts" or H > W
    m: dict = {"duration": round(dur, 2), "scenes": len(scenes), "cuts": max(0, len(scenes) - 1), "platform": platform}
    F: list[dict] = []

    frames = analysis_frames(video, W, H)
    if len(frames) < 3:
        F.append(find("P1", None, "video", f"only {len(frames)} analysis frames (video under 0.3 s or unreadable), visual checks skipped",
                      "render the full film before reviewing", "short_video"))
    else:
        diffs = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
        f0 = first_frame(video, W, H)
        if f0 is not None:
            d0 = detail(f0)
            med = float(np.median([detail(f) for f in frames[:: max(1, len(frames) // 40)]]))
            m["first_frame_detail"], m["median_frame_detail"] = round(d0, 1), round(med, 1)
            if med > 0 and d0 < 0.3 * med:
                F.append(find("P0", 0.0, "frame 0", f"first frame has {d0 / med:.0%} of the median detail (empty or fading in)",
                              "start the first scene fully built at t=0: headline and hero visible, no fade-in from black", "first_frame_empty"))
        win = 1.5 if shorts else 3.0
        dead = [(round(a / AN_FPS, 1), round(b / AN_FPS, 1)) for a, b in runs(diffs < 0.35, int(win * AN_FPS))]
        m["dead_stretches"] = dead
        for a, b in dead:
            F.append(find("P1", a, f"{a}-{b}s", f"{b - a:.1f} s with almost no pixel change (limit {win} s)",
                          "add a push-in, a text swap or a cut inside this window", "dead_stretch"))
        thr = max(1.0, 2.5 * float(np.median(diffs)))
        pk = [i for i in range(len(diffs)) if diffs[i] > thr and (i == 0 or diffs[i] >= diffs[i - 1])
              and (i == len(diffs) - 1 or diffs[i] > diffs[i + 1])]
        rate = len(pk) / max(dur, 0.1)
        ce = float((brief.get("pacing") or {}).get("change_every") or cfg.get("pacing", {}).get("change_every") or 0)
        m["changes_per_s"] = round(rate, 2)
        if ce:
            m["target_changes_per_s"] = round(1 / ce, 2)
            if rate < 0.6 / ce:
                F.append(find("P1", None, "whole film", f"{rate:.2f} visual changes/s vs {1 / ce:.2f} asked (change_every {ce} s)",
                              f"add a change every {ce} s: swap the object, move the camera or reveal a new element", "low_change_rate"))

    voice_iv = [(float(l["at"]), float(l["at"]) + float(l.get("dur", 0))) for l in lines]
    narr = sum(b - a for a, b in voice_iv)
    m["narration_share"] = round(narr / dur, 2) if dur else 0
    gap_lim = 0.6                                       # every format: the narration drives time, so unplanned silence stays small
    gaps = []
    for k in range(len(voice_iv) - 1):
        g = voice_iv[k + 1][0] - voice_iv[k][1]
        gaps.append(g)
        lim = gap_lim + min(float(lines[k + 1].get("pause") or 0), 0.8)     # a line may ask for a pause (`pause:` in the storyboard)
        if g > lim:
            F.append(find("P1", voice_iv[k][1], f"line {k + 1} to {k + 2}", f"{g:.2f} s of dead air after the line (limit {lim:.1f} s)",
                          f"pull line {k + 2} earlier by {g - lim:.2f} s or fill with a sound/visual beat", "dead_air_after_voice"))
    if gaps:
        sg = sorted(gaps)
        m["line_gap_median"] = round((sg[len(sg) // 2] if len(sg) % 2 else (sg[len(sg) // 2 - 1] + sg[len(sg) // 2]) / 2), 2)
        m["line_gap_max"] = round(max(gaps), 2)
    if lines:       # the hook: short, and the voice is already speaking
        n0, st0 = len(str(lines[0].get("display", "")).split()), float(lines[0]["at"])
        if n0 >= 10 or st0 > 0.2:
            F.append(find("P1", st0, "first line", f"hook has {n0} words and starts at {st0:.2f} s (under 10 words, within 0.2 s)",
                          "shorten the opening line and start it on frame 0", "weak_hook"))
    inner = []
    for a, b in zip(words, words[1:]):
        g = b["t0"] - a["t1"]
        if g > 0.45 and any(s - 0.05 <= a["t0"] and b["t1"] <= e + 0.05 for s, e in voice_iv):
            inner.append((round(a["t1"], 2), round(g, 2)))
            F.append(find("P2", a["t1"], f"between '{a['w']}' and '{b['w']}'", f"{g:.2f} s gap inside a line",
                          "trim the pause in the voice track or re-cut the take", "inner_voice_gaps"))
    m["inner_gaps"] = inner
    wps = []
    for k, l in enumerate(lines):
        n = len(str(l.get("display", "")).split())
        d = float(l.get("dur") or 0)
        if d > 0:
            r_ = n / d
            wps.append(round(r_, 2))
            if r_ > 3.6:   # the target pace is 2.8-3.3 words/s
                F.append(find("P1", l["at"], f"line {k + 1}", f"{r_:.1f} words/s is too fast to follow", "split the line or cut words", "words_per_second"))
    m["words_per_second"] = wps
    tgt = brief.get("length")
    m["target_length"] = tgt
    if tgt and dur and abs(dur - float(tgt)) / float(tgt) > 0.15:
        F.append(find("P1", None, "whole film", f"{dur:.1f} s vs target {tgt} s ({(dur - float(tgt)) / float(tgt):+.0%})",
                      "cut or add scenes until length is within 15% of the brief", "length_vs_target"))

    unread = []
    # hold rule = silent reading; captions of spoken words are read along with the voice
    for c in ([] if tl.get("voice_lines") else cues):
        n = len(str(c.get("text", "")).split())
        need = 0.5 + 0.3 * n
        hold = float(c["end"]) - float(c["start"])
        if hold < need - 0.01:
            unread.append(round(c["start"], 2))
            F.append(find("P0", c["start"], f"caption '{str(c.get('text'))[:30]}'", f"on screen {hold:.2f} s, needs {need:.2f} s ({n} words)",
                          f"hold the group {need - hold:.2f} s longer or split it", "unread_lines"))
    m["unread_caption_groups"] = unread

    cuts = [float(s["t0"]) for s in scenes[1:]]
    for t in cuts:
        for w in words:
            if w["t0"] + 0.03 < t < w["t1"] - 0.03:
                F.append(find("P0", t, "cut", f"cut lands inside the word '{w['w']}'",
                              f"move the cut to {w['t1']:.2f} s (word end) or {w['t0']:.2f} s (word start)", "cut_on_word"))
                break
    for a, b in zip(scenes, scenes[1:]):
        if a.get("type") and a.get("type") == b.get("type"):
            F.append(find("P2", b["t0"], f"{a.get('id')} to {b.get('id')}", f"two {a['type']} scenes in a row",
                          "change the layout (scale, side or object) or merge the two scenes", "repeated_layout"))

    try:
        import dissect
        x = dissect.load_audio(video)
        if len(x) < dissect.SR // 5:
            raise ValueError("no audio stream")
        Fe = dissect.stft_feats(x)
        t, rms = Fe["t"], Fe["rms"]
        quiet = rms < -40
        for s, e in voice_iv:
            quiet &= ~((t >= s) & (t <= e))
        sil = [(round(float(t[a]), 1), round(float(t[min(b, len(t) - 1)]), 1)) for a, b in runs(quiet, 50)]
        m["silent_stretches"] = sil
        for a, b in sil:
            F.append(find("P1", a, f"{a}-{b}s", f"{b - a:.1f} s silent (no voice, below -40 dBFS)", "lay a music bed or a sound under it", "silent_stretch"))
        ev = [e for e in dissect.classify_events(Fe) if e["kind"] != "typing/click-run"]
        m["sfx_per_10s"] = round(len(ev) * 10 / max(dur, 0.1), 1)
        if cuts:
            hit = sum(any(c - 0.15 <= e["t"] <= c + 0.05 for e in ev) for c in cuts)
            m["cuts_with_sound"] = round(hit / len(cuts), 2)
            if hit / len(cuts) < 0.5:
                F.append(find("P1", None, "cuts", f"only {hit}/{len(cuts)} cuts have a sound event within 0.15 s",
                              "put a hit, whoosh or tick on each cut (sfx.py)", "sfx_density"))
    except Exception as e:  # missing audio stream or decode failure
        m["audio"] = f"skipped: {str(e)[:80] or 'no audio stream'}"
        F.append(find("P1", None, "audio", "no audio could be read from final.mp4, audio checks skipped",
                      "check the mix step produced an audio track", "no_audio"))
    m["text_contrast_lint"] = "skipped (use stills.mjs --lint)"
    F.sort(key=lambda f: (f["sev"], f["t"] if f["t"] is not None else 1e9))
    return m, F


# ---------------------------------------------------------------- report
def write_md(path: Path, project: Path, platform: str, m: dict, F: list[dict], beats: list[str]) -> None:
    old = ""
    if path.exists():
        txt = path.read_text(encoding="utf-8")
        if SECTION in txt:
            tail = txt.split(SECTION, 1)[1]
            old = re.split(r"\n(?=## |Never score)", tail, maxsplit=1)[0].strip("\n")
    L = [f"# Review: {project.name} ({platform})", "", "| measure | value |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in m.items()]
    L += ["", "## Findings", ""]
    L += [f"- {f['sev']} t={'-' if f['t'] is None else str(f['t']) + 's'} · {f['where']} · {f['problem']} → {f['fix']}" for f in F] or ["- none"]
    L += ["", f"Sheets: build/{platform}/review/ (sheet-beats.jpg, sheet-cuts.jpg, sheet-hook.jpg). Scenes: {', '.join(beats)}", "",
          SECTION, "", old or PLACEHOLDER, "", NOTE, ""]
    path.write_text("\n".join(L), encoding="utf-8")


def review(project, platform: str = "shorts") -> dict:
    project = ensure_project(project)
    vid = project / "build" / platform / "final.mp4"
    tlp = project / "build" / f"timeline-{platform}.json"
    if not vid.exists():
        raise FishError(f"{vid} not found: render the {platform} cut first")
    tl = load_json(tlp)
    if not tl:
        raise FishError(f"{tlp} not found or empty")
    cfg = project_config(project)
    out = project / "build" / platform / "review"
    out.mkdir(parents=True, exist_ok=True)
    dur = float(tl.get("duration") or 0)
    last = max(dur - 0.05, 0)

    def clamp(t):
        return min(max(t, 0), last)

    scenes = tl.get("scenes", [])
    aspect = int(tl.get("H", 1920)) / int(tl.get("W", 1080))
    tw = PHONE_W // 2 + 60

    items = []
    for s in scenes:
        t0, t1 = float(s["t0"]), float(s["t1"])
        for tag, t in (("start", t0 + 0.05), ("mid", (t0 + t1) / 2), ("end", t1 - 0.05)):
            items.append((grab(vid, clamp(t)), f"{s.get('id')} {tag} {clamp(t):.2f}s"))
    sheet(items, out / "sheet-beats.jpg", 6, tw, aspect)

    cutitems = [(grab(vid, clamp(float(s["t0"]) + d)), f"cut {float(s['t0']):.2f} {d:+.2f}") for s in scenes[1:] for d in (-0.2, -0.07, 0.07, 0.2)]
    sheet(cutitems or [(grab(vid, 0), "no cuts (single scene)")], out / "sheet-cuts.jpg", 4 if cutitems else 1, tw, aspect)
    sheet([(grab(vid, clamp(t)), f"{t}s") for t in (0, 0.1, 0.25, 0.5, 1, 1.5, 2, 3)], out / "sheet-hook.jpg", 4, tw, aspect)

    m, F = run_checks(vid, tl, cfg, platform)
    save_json(out / "checks.json", {"measures": m, "findings": F})
    write_md(project / "REVIEW.md", project, platform, m, F, [str(s.get("id")) for s in scenes])
    log(f"review: {len(F)} findings ({sum(f['sev'] == 'P0' for f in F)} P0) -> {project / 'REVIEW.md'}")
    return {"measures": m, "findings": F, "dir": str(out), "md": str(project / "REVIEW.md")}


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Contact sheets and measured findings for a rendered cut.")
    ap.add_argument("project")
    ap.add_argument("--platform", default="shorts")
    a = ap.parse_args(argv)
    review(a.project, a.platform)
    return 0


if __name__ == "__main__":
    main_guard(cli)
