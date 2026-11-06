"""Captions: word timings -> caption cues -> SRT / VTT, plus checks and an
optional ffmpeg burn-in.

    python scripts/captions.py <project> [--platform youtube]        write SRT + VTT from the timeline
    python scripts/captions.py check <file.srt> [--max-chars 42]       lint a subtitle file
    python scripts/captions.py burn <in.mp4> <subs.srt> <out.mp4>      burn in with libass (fallback path)

Normally captions are burned in by the stage itself (branded, word-lit)
from timeline.captions.cues; SRT/VTT always ship alongside the video.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from fvcore import FishError, ffmpeg_bin, fmt_time, load_json, log, main_guard, run

BREAK_AFTER = re.compile(r"[.!?…:;]$|[,—–]$")


def chunk_words(words: list[dict], max_chars: int = 42, max_lines: int = 2, max_dur: float = 6.0, min_dur: float = 0.9) -> list[dict]:
    """Group timed words [{w, t0, t1}] into caption cues.

    A cue holds at most max_chars * max_lines characters, prefers to end at
    punctuation, never spans a pause longer than 0.6 s, and never lasts
    longer than max_dur. Returns [{start, end, text, words}], times absolute.
    """
    cues: list[dict] = []
    cur: list[dict] = []
    limit = max_chars * max_lines

    def flush():
        if cur:
            cues.append({"start": cur[0]["t0"], "end": cur[-1]["t1"], "text": " ".join(w["w"] for w in cur), "words": [dict(w) for w in cur]})
            cur.clear()

    for i, w in enumerate(words):
        if cur:
            cand = " ".join(x["w"] for x in cur) + " " + w["w"]
            gap = w["t0"] - cur[-1]["t1"]
            # the cue must actually wrap into the allowed lines: total length alone can leave no valid split
            lines = wrap_lines(cand, max_chars, max_lines)
            bad_wrap = len(lines) > max_lines or any(len(l) > max_chars for l in lines)
            if len(cand) > limit or bad_wrap or gap > 0.6 or w["t1"] - cur[0]["t0"] > max_dur:
                flush()
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        length = len(" ".join(x["w"] for x in cur))
        if BREAK_AFTER.search(w["w"]) and (length >= limit * 0.45 or (nxt and nxt["t0"] - w["t1"] > 0.35)):
            flush()
    flush()
    # a caption never floats a lone connecting word ("and", "the"): join it to the phrase it belongs to
    k = 0
    while k < len(cues):
        c = cues[k]
        if len(c["words"]) == 1 and not BREAK_AFTER.search(c["words"][0]["w"]) and len(c["words"][0]["w"].strip(".,;:!?\"'")) <= 4:
            if k + 1 < len(cues) and len(c["text"]) + 1 + len(cues[k + 1]["text"]) <= limit:
                n = cues[k + 1]
                n["words"] = c["words"] + n["words"]
                n["text"] = c["text"] + " " + n["text"]
                n["start"] = c["start"]
                cues.pop(k)
                continue
            if k > 0 and len(cues[k - 1]["text"]) + 1 + len(c["text"]) <= limit:
                pr = cues[k - 1]
                pr["words"] += c["words"]
                pr["text"] += " " + c["text"]
                pr["end"] = c["end"]
                cues.pop(k)
                continue
        k += 1
    # timing: hold each cue until the next one starts (or 0.45 s after its last word)
    for k, c in enumerate(cues):
        nxt = cues[k + 1]["start"] if k + 1 < len(cues) else float("inf")
        end = min(c["end"] + 0.45, nxt)            # linger a little, never into the next cue
        end = max(end, min(c["start"] + min_dur, nxt))  # but stay up long enough to read
        c["start"], c["end"] = round(c["start"], 3), round(end, 3)
    return cues


def wrap_lines(text: str, max_chars: int = 42, max_lines: int = 2) -> list[str]:
    """Balanced line breaks: two lines of similar length beat one long + one short."""
    words = text.split()
    if len(text) <= max_chars or max_lines == 1:
        return [text]
    best, best_score = [text], 1e9
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if len(a) > max_chars or len(b) > max_chars:
            continue
        score = abs(len(a) - len(b)) - (8 if BREAK_AFTER.search(words[i - 1]) else 0)
        if score < best_score:
            best, best_score = [a, b], score
    return best


def to_srt(cues: list[dict], max_chars: int = 42, max_lines: int = 2) -> str:
    out = []
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{fmt_time(c['start'])} --> {fmt_time(max(c['start'] + 0.2, c['end'] - 0.04))}\n" + "\n".join(wrap_lines(c["text"], max_chars, max_lines)) + "\n")
    return "\n".join(out)


def to_vtt(cues: list[dict], max_chars: int = 42, max_lines: int = 2) -> str:
    out = ["WEBVTT", ""]
    for c in cues:
        out.append(f"{fmt_time(c['start'], '.')} --> {fmt_time(max(c['start'] + 0.2, c['end'] - 0.04), '.')}")
        out.extend(wrap_lines(c["text"], max_chars, max_lines))
        out.append("")
    return "\n".join(out)


def parse_srt(text: str) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", text.strip().replace("\r\n", "\n")):
        lines = block.strip().split("\n")
        m = next((re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", l) for l in lines if "-->" in l), None)
        if not m:
            continue
        g = list(map(int, m.groups()))
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        idx = next(i for i, l in enumerate(lines) if "-->" in l)
        cues.append({"start": start, "end": end, "lines": lines[idx + 1:], "text": " ".join(lines[idx + 1:])})
    return cues


def check_cues(cues: list[dict], max_chars: int = 42, max_lines: int = 2, max_cps: float = 20, duration: float | None = None) -> list[str]:
    """Problems in a cue list: overlaps, long lines, too many lines, reading speed, out of range."""
    issues = []
    for i, c in enumerate(cues):
        lines = c.get("lines") or wrap_lines(c["text"], max_chars, max_lines)
        d = c["end"] - c["start"]
        if d <= 0:
            issues.append(f"cue {i + 1}: non-positive duration")
            continue
        if len(lines) > max_lines:
            issues.append(f"cue {i + 1}: {len(lines)} lines (max {max_lines})")
        for l in lines:
            if len(l) > max_chars:
                issues.append(f"cue {i + 1}: line of {len(l)} chars (max {max_chars}): {l[:50]}")
        cps = len(c["text"]) / d
        if cps > max_cps * 1.25:
            issues.append(f"cue {i + 1}: {cps:.0f} chars/s (max {max_cps})")
        if i and c["start"] < cues[i - 1]["end"] - 0.001:
            issues.append(f"cue {i + 1}: overlaps the previous cue")
        if duration is not None and c["end"] > duration + 0.05:
            issues.append(f"cue {i + 1}: ends after the video ({c['end']:.2f} > {duration:.2f})")
    return issues


def sync_check(cues: list[dict], words: list[dict], tol: float = 0.25) -> list[str]:
    """Every spoken word must fall inside a cue that contains it (within tol)."""
    issues = []
    for w in words:
        mid = (w["t0"] + w["t1"]) / 2
        if not any(c["start"] - tol <= mid <= c["end"] + tol for c in cues):
            issues.append(f"word '{w['w']}' at {mid:.2f}s is not covered by any caption")
    return issues


def write_files(project: Path, platform: str) -> dict:
    """SRT + VTT for one platform from its resolved timeline."""
    tl = load_json(Path(project) / "build" / f"timeline-{platform}.json")
    cap = tl.get("captions") or {}
    mc, ml = cap.get("max_chars", 42), cap.get("max_lines", 2)
    cues = cap.get("cues") or []
    d = Path(project) / "build" / platform
    d.mkdir(parents=True, exist_ok=True)
    srt, vtt = d / "captions.srt", d / "captions.vtt"
    srt.write_text(to_srt(cues, mc, ml), encoding="utf-8")
    vtt.write_text(to_vtt(cues, mc, ml), encoding="utf-8")
    txt = d / "transcript.txt"
    lines = [ln["display"] for sc in tl.get("voice_lines", []) for ln in [sc]]
    txt.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {"srt": str(srt), "vtt": str(vtt), "transcript": str(txt), "cues": len(cues)}


def burn(src: Path, subs: Path, out: Path, style: str = "FontName=Inter,FontSize=22,PrimaryColour=&H00141A1A,BackColour=&H80F2EDE3,BorderStyle=3,Outline=6,Shadow=0,MarginV=60") -> Path:
    """Burn an SRT into a video with libass (used when the stage cannot burn captions, e.g. for third-party footage)."""
    p = str(subs).replace("\\", "/").replace(":", "\\:")
    run([ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(src), "-vf", f"subtitles='{p}':force_style='{style}'", "-c:a", "copy", str(out)])
    return out


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("args", nargs="+")
    ap.add_argument("--platform", default=None)
    ap.add_argument("--max-chars", type=int, default=42)
    ap.add_argument("--max-lines", type=int, default=2)
    a = ap.parse_args(argv)
    if a.args[0] == "check":
        cues = parse_srt(Path(a.args[1]).read_text(encoding="utf-8"))
        issues = check_cues(cues, a.max_chars, a.max_lines)
        for i in issues:
            log("  " + i)
        log(f"{len(cues)} cues, {len(issues)} issues")
        return 1 if issues else 0
    if a.args[0] == "burn":
        if len(a.args) < 4:
            raise FishError("usage: captions.py burn <in.mp4> <subs.srt> <out.mp4>")
        burn(Path(a.args[1]), Path(a.args[2]), Path(a.args[3]))
        return 0
    project = Path(a.args[0])
    from fvcore import project_config
    plats = [a.platform] if a.platform else project_config(project)["brief"].get("platforms", ["youtube"])
    for p in plats:
        log(f"{p}: {write_files(project, p)}")
    return 0


if __name__ == "__main__":
    main_guard(cli)
