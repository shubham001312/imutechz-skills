"""Render: frames -> score -> voice -> mix -> loudness -> encode, per platform.

    python scripts/render.py <project> [--platform youtube,linkedin] [--scale 0.5] [--workers 4]
                             [--from 10 --to 20] [--fast] [--no-voice] [--no-music]

For each platform:
  1. storyboard.build      re-resolve every timeline (uses the voice clips if present)
  2. frames.mjs            deterministic frames in parallel headless workers -> build/<p>/video.mp4
  3. sfx.py + music.mjs    sample SFX (sfx-samples.wav) + synth SFX (sfx.wav) + score (music.wav),
                           or a library track from assets/music/ (music-track.wav)
  4. voice.build_track     narration clips placed on one track + the voice post chain -> voice.wav
  5. mix                   three stems: voice -16 LUFS; music 10 dB under, carved + ducked ~6 dB; SFX on top, not ducked
  6. loudnorm (two pass)   to the platform target (-14 LUFS integrated, -1.5 dBTP)
  7. encode                H.264 High, yuv420p, AAC 48 kHz, +faststart -> build/<p>/final.mp4
  8. captions              SRT + VTT next to it
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from fvcore import (FishError, ensure_project, ffmpeg_bin, last_json_line, load_json, log, main_guard, node,
                    project_config, run, save_json, warn)
import captions as captions_mod
import storyboard as sbmod
import voice as voicemod


def loudnorm_filter(src: Path, target: float = -14, tp: float = -1.5, lra: float = 11) -> str:
    """Measure (pass 1) and return the linear pass-2 loudnorm filter string."""
    r = run([ffmpeg_bin(), "-hide_banner", "-i", str(src), "-af", f"loudnorm=I={target}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"], capture=True)
    err = r.stderr
    js = json.loads(err[err.rindex("{"): err.rindex("}") + 1])
    if js["input_i"] in ("-inf", "inf"):
        raise FishError(f"{src.name} is silent; nothing to normalise")
    return (f"loudnorm=I={target}:TP={tp}:LRA={lra}:measured_I={js['input_i']}:measured_TP={js['input_tp']}:"
            f"measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true")


# What a phone / small laptop speaker can actually reproduce: mono, nothing useful below ~300 Hz,
# a resonant bump near 2.5 kHz, little air. Levels are balanced through this, so the mix translates.
PHONE_SIM = "aformat=channel_layouts=mono,highpass=f=250:poles=1,highpass=f=200:poles=2,lowpass=f=10000,equalizer=f=2500:t=o:w=1.2:g=3"
LAPTOP_SIM = "aformat=channel_layouts=mono,highpass=f=180:poles=2,equalizer=f=700:t=o:w=1:g=-2,equalizer=f=3500:t=o:w=1:g=2,lowpass=f=14000"


def harmonics(label_in: str, label_out: str, drive_db: float, mix_db: float) -> str:
    """Psychoacoustic bass: saturate the lows, keep only the upper harmonics, blend them back.
    The ear infers the missing fundamental, so bass stays audible on speakers that cannot play it."""
    x = label_in.strip("[]")
    return (f"{label_in}asplit=2[{x}d][{x}w];"
            f"[{x}w]lowpass=f=220,volume={drive_db}dB,asoftclip=type=atan,highpass=f=150,highpass=f=150,lowpass=f=1200,volume={mix_db}dB[{x}h];"
            f"[{x}d][{x}h]amix=inputs=2:normalize=0{label_out}")


def lufs(src: Path, af: str | None = None) -> float | None:
    """Integrated loudness of a file (None when silent). af = a filter applied first, e.g. PHONE_SIM."""
    chain = f"{af},ebur128" if af else "ebur128"
    r = run([ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(src), "-af", chain, "-f", "null", "-"], capture=True, check=False)
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    m = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
    v = float(m.group(1)) if m else None
    return None if v is None or v < -70 else v


def _env(path: Path, af: str):
    """50 ms RMS envelope (dB) of a file heard through a speaker simulation."""
    import subprocess
    import numpy as np
    r = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(path), "-af", af, "-ac", "1", "-ar", "22050", "-f", "f32le", "-"], capture_output=True, check=True)
    x = np.frombuffer(r.stdout, dtype=np.float32)
    hop = 1102
    n = len(x) // hop
    if not n:
        return np.zeros(0)
    return 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)


def _sfx_trim(sfx: list[Path], voice: Path | None, gv: float | None, mixcfg: dict, report: dict) -> float:
    """Integrated loudness hides short sounds, so calibrate by events: on a phone, a typical SFX event should
    peak mix.sfx_under_voice_db below typical speech. Returns the gain for the SFX stems (bounded)."""
    if not sfx or not voice:
        return 0.0
    try:
        import numpy as np
        v = _env(voice, PHONE_SIM) + (gv or 0)
        v = v[v > -60]
        ev = []
        for s in sfx:
            e = _env(s, PHONE_SIM)
            e = e[e > -60]
            if len(e):
                ev.append(e)
        if not len(v) or not ev:
            return 0.0
        typical = float(np.percentile(np.concatenate(ev), 75))
        speech = float(np.median(v))
        want = speech + mixcfg.get("sfx_under_voice_db", -7) - typical
        g = max(-6.0, min(mixcfg.get("sfx_max_boost_db", 12), want))
        report.update(sfx_event=round(typical + g, 1), speech=round(speech, 1), sfx_trim=round(g, 1))
        return g
    except Exception as e:  # numpy missing or decode error: keep the authored levels
        warn(f"sfx calibration skipped: {type(e).__name__}")
        return 0.0


def _harm_af(drive: float, hmix: float) -> str:
    """The same harmonics as harmonics(), as a single -af chain, for measuring."""
    return (f"asplit=2[d][w];[w]lowpass=f=220,volume={drive}dB,asoftclip=type=atan,highpass=f=150,highpass=f=150,lowpass=f=1200,volume={hmix}dB[h];"
            f"[d][h]amix=inputs=2:normalize=0")


def prepare_track(track: Path, build: Path, duration: float, fade: float = 1.5, offset: float = 0.0) -> Path:
    """A library music file -> looped/trimmed to the timeline, faded out, 48 kHz stereo.
    offset: start the track that many seconds in (brief.music.offset; see scripts/beats.py)."""
    out = build / "music-track.wav"
    seek = ["-ss", f"{offset:.3f}"] if offset and offset > 0 else []
    run([ffmpeg_bin(), "-y", "-loglevel", "error", "-stream_loop", "-1", *seek, "-i", str(track), "-af",
         f"aformat=channel_layouts=stereo,atrim=0:{duration + 0.6:.3f},afade=t=out:st={max(0, duration - fade):.3f}:d={fade}",
         "-ar", "48000", "-c:a", "pcm_f32le", str(out)])
    return out


def _run_mix(cmd: list, duration: float, timeout: float | None = None, tries: int = 2) -> None:
    """Run the stem-mix ffmpeg with a timeout. It has been seen to stall at end of stream (0% CPU, output complete),
    so a hung attempt is killed and retried once; after that the error says what to do. Never waits forever."""
    import os
    limit = timeout or float(os.environ.get("FISH_MIX_TIMEOUT") or max(120.0, duration * 4))
    for n in range(1, tries + 1):
        try:
            run(cmd, timeout=limit)
            return
        except FishError as e:
            if "timed out" not in str(e):
                raise
            log(f"mix ffmpeg stalled (attempt {n}/{tries}, {limit:.0f}s)")
    raise FishError(f"the audio mix ffmpeg stalled {tries} times (no result in {limit:.0f}s each). Re-run `fishvideo render`; "
                    f"it resumes from build/. If it persists, raise FISH_MIX_TIMEOUT (seconds) or run with fewer sfx/music stems.")


def mix_audio(build: Path, music: Path | None, voice: Path | None, duration: float, mixcfg: dict, prof: dict,
              sfx: list[Path] | None = None) -> Path:
    """Three stems -> loudness-normalised 48 kHz stereo WAV (references/sound-design.md).

    voice  -> gain to mix.voice_lufs
    music  -> bass harmonics, then the gain that puts it music_under_voice_db under the voice ON A PHONE
              SPEAKER (capped by music_max_fullband_db so headphones stay balanced); sidechain-ducked
    sfx    -> bass harmonics so impacts survive on small speakers; summed on top, NOT ducked
    """
    ff = ffmpeg_bin()
    raw = build / "mix-raw.wav"
    dur = f"{duration + 0.6:.3f}"
    sfx = [s for s in (sfx or []) if s and Path(s).exists()]
    vl = mixcfg.get("voice_lufs", -16)
    inputs, chains, labels = [], [], []
    phone_report: dict = {}
    lv = gv = None
    if voice:
        lv = lufs(voice)
        gv = (vl - lv) if lv is not None else 0
        vi = len(inputs); inputs.append(voice)
        split = "asplit=2[vk][vo]" if music else "anull[vo]"
        chains.append(f"[{vi}:a]aformat=channel_layouts=stereo,volume={gv:.2f}dB,{split}")
        labels.append("[vo]")
    if music:
        lm = lufs(music)
        under = mixcfg.get("music_under_voice_db", -10)
        target = (vl + under) if voice else vl
        gm = (target - lm) if lm is not None else 0
        mi = len(inputs); inputs.append(music)
        tr = mixcfg.get("translate") or {}
        drive, hmix = tr.get("music_drive_db", 14), tr.get("music_harmonics_db", -4)
        c = f"[{mi}:a]aformat=channel_layouts=stereo,highpass=f=30,extrastereo=m={tr.get('music_width', 0.85)},volume={gm:.2f}dB"
        if voice:
            # calibrate in the phone domain: harmonics add mid energy, so the gain is measured through the same chain
            phone_v = lufs(voice, PHONE_SIM)
            phone_m = lufs(music, f"aformat=channel_layouts=stereo,highpass=f=30,{_harm_af(drive, hmix)},{PHONE_SIM}")
            if phone_v is not None and phone_m is not None and lv is not None:
                want = (phone_v + gv + under) - phone_m                                 # the music gain that hits the phone target
                cap = (vl + mixcfg.get("music_max_fullband_db", -6)) - (lm if lm is not None else vl)  # headphones must not blow up
                gm = min(want, cap)
                c = f"[{mi}:a]aformat=channel_layouts=stereo,highpass=f=30,extrastereo=m={tr.get('music_width', 0.85)},volume={gm:.2f}dB"
                phone_report.update(voice=round(phone_v + gv, 1), music=round(phone_m + gm, 1), gap=round(phone_v + gv - phone_m - gm, 1),
                                    music_gain=round(gm, 1), capped=bool(want > cap))
            c += f",equalizer=f=1100:t=o:w=2.2:g={mixcfg.get('music_carve_db', -1.5)}"
            d = mixcfg["duck"]
            chains.append(c + "[mq0]")
            chains.append(harmonics("[mq0]", "[mq]", drive, hmix))
            # multiband duck: only the mid band (where words live) moves, so the bass harmonics and the air keep the music audible
            chains.append(f"[mq]acrossover=split=150 4000:order=4th[ml][mm][mt]")
            chains.append(f"[mm][vk]sidechaincompress=threshold={d['threshold']}:ratio={d['ratio']}:attack={d['attack']}:release={d['release']}:makeup={d.get('makeup', 1)}[mmd]")
            chains.append("[ml][mmd][mt]amix=inputs=3:normalize=0[md]")
        else:
            chains.append(c + "[mq0]")
            chains.append(harmonics("[mq0]", "[md]", drive, hmix))
        labels.append("[md]")
    sfx_gain = mixcfg.get("sfx_gain_db", 0) + _sfx_trim(sfx, voice, gv, mixcfg, phone_report)
    for s in sfx:
        si = len(inputs); inputs.append(s)
        tr = mixcfg.get("translate") or {}
        chains.append(f"[{si}:a]aformat=channel_layouts=stereo,volume={sfx_gain:.2f}dB[s{si}0]")
        chains.append(harmonics(f"[s{si}0]", f"[s{si}]", tr.get("sfx_drive_db", 16), tr.get("sfx_harmonics_db", -6)))
        labels.append(f"[s{si}]")
    if not inputs:
        run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", dur, "-c:a", "pcm_f32le", str(raw)])
        return raw
    fc = ";".join(chains) + ";" + "".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest,atrim=0:{dur}[out]"
    graph = build / "mix-graph.txt"
    graph.write_text(fc, encoding="utf-8")
    args = [ff, "-y", "-loglevel", "error"]
    for i in inputs:
        args += ["-i", str(i)]
    _run_mix(args + ["-filter_complex_script", str(graph), "-map", "[out]", "-ar", "48000", "-c:a", "pcm_f32le", str(raw)], duration)
    save_json(build / "mix.json", {"voice_lufs_target": vl if voice else None,
                                   "music_offset_db": mixcfg.get("music_under_voice_db", -10) if (voice and music) else None,
                                   "music": str(music) if music else None, "sfx_stems": [str(s) for s in sfx],
                                   "sfx_lufs": [lufs(s) for s in sfx], "duck": mixcfg.get("duck"), "phone": phone_report})
    target, tp = prof.get("loudness", mixcfg["loudness"]), prof.get("true_peak", mixcfg["true_peak"])
    # normalise with 0.5 dB of margin, then a brickwall limiter just under the ceiling:
    # linear loudnorm alone can overshoot the true-peak target after AAC encoding
    af = loudnorm_filter(raw, target, tp - 0.5, mixcfg.get("lra", 11))
    af += f",alimiter=limit={10 ** ((tp - 1.2) / 20):.4f}:attack=2:release=60:level=0"
    out = build / "mix.wav"
    run([ff, "-y", "-loglevel", "error", "-i", str(raw), "-af", af, "-ar", "48000", "-c:a", "pcm_s24le", str(out)])
    return out


def encode(video: Path, audio: Path, out: Path, prof: dict, *, ss: float = 0, dur: float | None = None, fast: bool = False) -> Path:
    args = [ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(video), "-ss", f"{ss:.3f}"]
    if dur:
        args += ["-t", f"{dur:.3f}"]
    args += ["-i", str(audio), "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-preset", "veryfast" if fast else "slow", "-crf", str(prof.get("crf", 18)),
             "-maxrate", prof.get("maxrate", "16M"), "-bufsize", prof.get("bufsize", "32M"), "-profile:v", "high", "-pix_fmt", "yuv420p",
             "-r", str(prof.get("fps", 30)), "-g", str(int(prof.get("fps", 30)) * 2), "-c:a", "aac", "-b:a", prof.get("audio_bitrate", "192k"), "-ar", "48000", "-ac", "2",
             "-shortest", "-movflags", "+faststart", str(out)]
    run(args)
    return out


def _music_track(project: Path, cfg: dict) -> Path | None:
    """brief.music.track (project-relative), else the first file in assets/music/; None = synthesised score."""
    m = cfg["brief"].get("music") or {}
    if m.get("source") == "synth":
        return None
    if m.get("track"):
        p = project / m["track"]
        if p.exists():
            return p
        warn(f"music.track {m['track']} not found: using the synthesised score")
        return None
    d = project / "assets" / "music"
    files = sorted(f for f in d.iterdir() if f.suffix.lower() in (".mp3", ".wav", ".ogg", ".flac", ".m4a")) if d.exists() else []
    return files[0] if files else None


def render_platform(project: Path, platform: str, *, scale: float = 1, workers: int = 4, t_from: float | None = None, t_to: float | None = None,
                    fast: bool = False, use_voice: bool = True, use_music: bool = True) -> dict:
    project = ensure_project(project)
    cfg = project_config(project)
    prof = cfg["platforms"][platform]
    build = project / "build" / platform
    build.mkdir(parents=True, exist_ok=True)
    tl = load_json(project / "build" / f"timeline-{platform}.json")
    preview = t_from is not None or t_to is not None
    args = [project, "--platform", platform, "--workers", workers, "--scale", scale, "--preset", "veryfast" if fast else "medium"]
    if preview:
        args += ["--from", t_from or 0, "--to", t_to if t_to is not None else tl["duration"]]
    log(f"[{platform}] frames ({tl['W']}x{tl['H']} x{scale}, {tl['duration']:.1f}s)")
    r = node("frames.mjs", *args, capture=False)
    video = build / ("video-preview.mp4" if preview else "video.mp4")
    info = load_json(build / "info.json")
    if info.get("errors"):
        warn(f"[{platform}] the stage reported {len(info['errors'])} page errors: {info['errors'][:2]}")
    music, sfx_stems = None, []
    if use_music:
        import sfx as sfxmod
        sres = sfxmod.build(project, platform)
        log(f"[{platform}] score + synth sfx")
        node("music.mjs", project, "--platform", platform, capture=True)
        music = build / "music.wav"
        track = _music_track(project, cfg)
        if track:
            log(f"[{platform}] music: library track {track.name} (licence must be in assets/credits.json)")
            music = prepare_track(track, build, tl["duration"], offset=float((cfg["brief"].get("music") or {}).get("offset") or 0))
        sfx_stems = [build / "sfx.wav"] + ([Path(sres["wav"])] if sres.get("wav") else [])
    vtrack = None
    if use_voice and any(v.get("wav") for v in tl.get("voice_lines", [])):
        log(f"[{platform}] voice track")
        clips = load_json(project / "build" / "voice" / "clips.json", default={})
        vtrack = voicemod.build_track(project, tl, build / "voice.wav", clips.get("post") if clips.get("provider") == "recording" else (clips.get("post") or cfg["voice"].get("post")))
    elif use_voice and tl.get("voice_lines"):
        warn(f"[{platform}] narration is estimated only (no voice clips): rendering music only; run `fishvideo voice`")
    log(f"[{platform}] mix + loudness")
    mix = mix_audio(build, music, vtrack, tl["duration"], cfg["mix"], prof, sfx_stems)
    final = build / ("final-preview.mp4" if preview else "final.mp4")
    ss = t_from or 0
    dur = (t_to if t_to is not None else tl["duration"]) - ss if preview else None
    encode(video, mix, final, prof, ss=ss, dur=dur, fast=fast)
    caps = captions_mod.write_files(project, platform)
    log(f"[{platform}] wrote {final}")
    return {"platform": platform, "video": str(final), "duration": tl["duration"], "captions": caps, "voice": bool(vtrack), "preview": preview}


def render(project: Path, platforms: list[str] | None = None, **kw) -> list[dict]:
    import themes
    from fvcore import project_config as _pc
    themes.check_fonts(_pc(Path(project))["brief"])       # a theme's fonts must be installed: no silent fallback
    project = ensure_project(project)
    sbmod.build(project, quiet=True)
    cfg = project_config(project)
    plats = platforms or sbmod.platforms_of(cfg)
    return [render_platform(project, p, **kw) for p in plats]


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--platform", default=None, help="comma list (default: brief.platforms)")
    ap.add_argument("--scale", type=float, default=1.0, help="render resolution factor (0.5 = half size preview)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--from", dest="t_from", type=float, default=None)
    ap.add_argument("--to", dest="t_to", type=float, default=None)
    ap.add_argument("--fast", action="store_true", help="fast x264 presets (previews, tests)")
    ap.add_argument("--no-voice", action="store_true")
    ap.add_argument("--no-music", action="store_true")
    a = ap.parse_args(argv)
    res = render(Path(a.project), a.platform.split(",") if a.platform else None, scale=a.scale, workers=a.workers,
                 t_from=a.t_from, t_to=a.t_to, fast=a.fast, use_voice=not a.no_voice, use_music=not a.no_music)
    log(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    main_guard(cli)
