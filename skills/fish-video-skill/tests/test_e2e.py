"""End-to-end smoke tests: render real videos at one-third resolution and
verify them with qa.py. Slow (minutes); need Node, a Chromium browser,
ffmpeg and internet (edge-tts voice; the live site for the tour).

    .venv/Scripts/python -m pytest tests/test_e2e.py -m e2e -s

Outputs are kept in tests/_out/.
"""
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from conftest import FIX, OUT, ROOT

PY = sys.executable
CLI = str(ROOT / "scripts" / "fishvideo.py")
SCALE = "0.33334"  # 1920x1080 -> 640x360, 1080x1920 -> 360x640


def run_all(project: Path, name: str):
    # fixtures carry hand-written storyboards and no interview: --no-gate is for tests only
    r = subprocess.run([PY, CLI, "all", str(project), "--scale", SCALE, "--fast", "--workers", "4", "--name", name, "--no-gate"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout[-4000:], r.stderr[-2000:])
    assert r.returncode == 0, r.stderr[-1500:]
    return r


def qa_ok(project: Path, platform: str) -> dict:
    rep = json.loads((project / "build" / platform / "qa.json").read_text(encoding="utf-8"))
    fails = [c for c in rep["checks"] if c["status"] == "FAIL"]
    assert not fails, f"{platform} QA failures: {fails}"
    checks = {c["check"]: c for c in rep["checks"]}
    for k in ("codec", "resolution", "audio", "faststart", "duration", "loudness", "true peak", "captions", "text lint", "facts"):
        assert checks[k]["status"] == "PASS", (k, checks[k])
    return rep


def site_url() -> str:
    try:
        with urllib.request.urlopen("http://localhost:3000/", timeout=5) as r:
            if r.status == 200:
                return "http://localhost:3000/"
    except Exception:
        pass
    return "https://www.imutechz.in/"


@pytest.mark.e2e
@pytest.mark.network
def test_fictional_topic_video():
    project = OUT / "smoke"
    shutil.rmtree(project, ignore_errors=True)
    shutil.copytree(FIX / "smoke", project)
    run_all(project, "Smoke")
    for p in ("youtube", "shorts"):
        qa_ok(project, p)
    pkg = project / "out" / "Smoke"
    names = {str(f.relative_to(pkg)).replace("\\", "/") for f in pkg.rglob("*") if f.is_file()}
    s = "tidewell-in-16-seconds"
    for need in (f"video/{s}-youtube.mp4", f"video/{s}-shorts.mp4", f"captions/{s}-youtube.srt", "thumbnails/thumbnail-1280x720.png",
                 "thumbnails/cover-shorts.png", "metadata/transcript.txt", "metadata/metadata.json", "metadata/tags.txt",
                 "metadata/titles.txt", "metadata/credits.txt", "metadata/youtube-post.txt", "qa/qa.md", "README.md"):
        assert need in names, need
    meta = json.loads((pkg / "metadata" / "metadata.json").read_text(encoding="utf-8"))
    assert meta["voice"]["provider"] in ("edge-tts", "elevenlabs")
    # three stems were mixed: music, synth sfx and voice
    assert (project / "build" / "youtube" / "sfx.wav").exists()


@pytest.mark.e2e
@pytest.mark.network
def test_website_tour_video():
    project = OUT / "tour"
    shutil.rmtree(project, ignore_errors=True)
    shutil.copytree(FIX / "tour", project)
    url = site_url()
    sbf = project / "storyboard.yaml"
    sbf.write_text(sbf.read_text(encoding="utf-8").replace("http://localhost:3000/", url), encoding="utf-8")
    run_all(project, "Tour")
    rep = qa_ok(project, "youtube")
    meta = json.loads((project / "build" / "cap" / "home" / "meta.json").read_text(encoding="utf-8"))
    assert meta["count"] > 150 and "hero" in meta["marks"] and not meta["errors"]
