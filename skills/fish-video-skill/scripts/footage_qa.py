"""QA for one footage Short: duration, motion per 0.5 s window, loudness, transcript check, frame sheet.

    fishvideo footage qa <dir>     -> prints a report, writes build/qa.json + build/sheets/final.jpg, exits 1 on FAIL

Gates (spec.yaml `qa:` overrides): length min_len..max_len (default 15-30 s), every 0.5 s window moves (mean grey
frame difference at 270x480 >= motion_min, default 1.0: no static slide), median motion >= 2.0, the final audio
transcribes back to the script (ratio > 0.8). Then OPEN build/sheets/final.jpg: the numbers do not see a bad frame.
"""
import json, re, subprocess, sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from footage_voice import FF, norm, transcribe  # noqa: E402
from footage_tools import sheet  # noqa: E402


def motion(video):
    raw = subprocess.run([FF, "-loglevel", "error", "-i", str(video), "-vf", "scale=270:480,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 480, 270).astype(np.float32)
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    win = [float(d[i:i + 15].mean()) for i in range(0, len(d), 15)]
    return win


def loudness(video):
    err = subprocess.run([FF, "-i", str(video), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    return float(m[-1]) if m else None


def run(vdir: Path):
    v = vdir / "out/video.mp4"
    dur = float(re.search(r"Duration: \d+:\d+:([\d.]+)", subprocess.run([FF, "-i", str(v)], capture_output=True, text=True).stderr).group(1))
    win = motion(v)
    lufs = loudness(v)
    hj = vdir / "build/heard_final.json"
    transcribe(v, hj)
    heard = " ".join(h["w"] for h in json.loads(hj.read_text()))
    words = json.loads((vdir / "build/words.json").read_text())
    import difflib
    a = [norm(x) for x in words["spoken"].split()]; b = [norm(x) for x in heard.split()]
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    sheet(str(v), str(vdir / "build/sheets/final.jpg"), 1.0, 8)
    rep = {"duration": dur, "motion_min": round(min(win), 2), "motion_median": round(float(np.median(win)), 2),
           "low_windows": [round(i * 0.5, 1) for i, x in enumerate(win) if x < 1.0], "lufs": lufs, "transcript_match": round(ratio, 3), "heard": heard}
    (vdir / "build/qa.json").write_text(json.dumps(rep, indent=1))
    q = {"min_len": 15, "max_len": 30, "motion_min": 1.0, "motion_median": 2.0, "transcript": 0.8, **((yaml.safe_load((vdir / "spec.yaml").read_text()) or {}).get("qa") or {})}
    fails = [m for m, bad in (("length", not q["min_len"] <= dur <= q["max_len"]), ("motion (static window)", min(win) < q["motion_min"]),
                              ("motion median", np.median(win) < q["motion_median"]), ("transcript", ratio <= q["transcript"])) if bad]
    rep["fails"] = fails
    (vdir / "build/qa.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1)); print("PASS" if not fails else "FAIL: " + ", ".join(fails))
    return not fails


if __name__ == "__main__":
    sys.exit(0 if run(Path(sys.argv[1])) else 1)
