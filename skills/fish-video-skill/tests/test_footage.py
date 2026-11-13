"""Offline tests for the footage pipeline (fishvideo footage): script markup, word alignment, path resolution, synth SFX,
a real half-resolution render of a generated clip, the motion meter, and the post texts. No network, no key, no whisper."""
import json
import subprocess
import wave

import numpy as np
import pytest
import yaml

import footage
import footage_package
import footage_qa
import footage_render
import footage_tools
import footage_voice
from fvcore import ffmpeg_bin

FF = ffmpeg_bin()


def test_parse_anchors_and_shown_words():
    units, spoken = footage_voice.parse("{hook}Every QR code survives [eighteen percent|18%] damage. {end}")
    assert spoken == "Every QR code survives eighteen percent damage."
    assert units[0]["anchors"] == ["hook"] and units[0]["spoken"] == ["Every"]
    shown = [u for u in units if u["shown"].startswith("18%")][0]
    assert shown["spoken"] == ["eighteen", "percent"] and shown["shown"] == "18%"
    damage = [u for u in units if u["spoken"] == ["damage."]][0]
    assert damage["shown"] == "damage."
    assert units[-1] == {"spoken": [], "shown": "", "anchors": ["end"]}


def test_shown_override_keeps_trailing_punctuation():
    units, spoken = footage_voice.parse("[Imu Run.|IMURUN.] {x}Go.")
    assert spoken == "Imu Run. Go." and units[0]["shown"] == "IMURUN."


def test_align_matches_and_interpolates():
    heard = [{"w": "your", "s": 0.0, "e": 0.2}, {"w": "phone", "s": 0.25, "e": 0.5}, {"w": "light", "s": 1.2, "e": 1.5}]
    t = footage_voice.align(["Your", "phone", "sees", "light."], heard, 2.0)
    assert t[0] == (0.0, 0.2) and t[1] == (0.25, 0.5) and t[3] == (1.2, 1.5)
    assert 0.5 <= t[2][0] < 1.2                                   # the unheard word sits in the gap


def test_synth_sfx_and_resolve(tmp_path):
    names = footage_tools.synth_sfx()
    assert {"s-whoosh.wav", "s-hit.wav", "s-pop.wav", "s-boom.wav"} <= set(names)
    with wave.open(str(footage_tools.SFX_DIR / "s-hit.wav")) as w:
        assert w.getframerate() == 48000 and w.getnchannels() == 2 and w.getnframes() > 48000
    assert footage_render.resolve(tmp_path, "sfx/s-hit.wav") == footage_tools.SFX_DIR / "s-hit.wav"
    (tmp_path / "assets").mkdir(); (tmp_path / "assets/a.mp3").write_bytes(b"x")
    assert footage_render.resolve(tmp_path, "assets/a.mp3") == tmp_path / "assets/a.mp3"


def test_cli_new_writes_template(tmp_path):
    d = tmp_path / "short"
    assert footage.cli(["new", str(d)]) == 0
    spec = yaml.safe_load((d / "spec.yaml").read_text())
    assert spec["captions"] is False and "thumbnail" in spec and spec["shots"]
    assert (d / "assets").is_dir() and (d / "out").is_dir()


@pytest.fixture
def project(tmp_path):
    d = tmp_path / "p"
    for s in ("assets", "build", "out"):
        (d / s).mkdir(parents=True)
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=4",
                    "-pix_fmt", "yuv420p", str(d / "assets/clip.mp4")], check=True)
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=180:duration=2.5:sample_rate=48000",
                    "-ac", "1", str(d / "build/voice.wav")], check=True)
    (d / "build/words.json").write_text(json.dumps({
        "duration": 2.5, "anchors": {"hook": 0.0, "two": 1.2, "end": 2.5}, "spoken": "One two three four",
        "captions": [{"text": "One", "s": 0.0, "e": 0.5}, {"text": "two", "s": 0.6, "e": 1.1}, {"text": "three", "s": 1.2, "e": 1.8},
                     {"text": "four", "s": 1.9, "e": 2.4}]}))
    spec = {
        "title": "t", "script": "{hook}One two {two}three four{end}", "tail": 0.3,
        "shots": [{"at": "hook", "src": "assets/clip.mp4", "in": 0.0, "fx": 0.5, "fy": 0.5, "z0": 1.0, "z1": 1.3},
                  {"at": "two", "src": "assets/clip.mp4", "in": 2.0, "card": [0.1, 0.1, 0.9, 0.9], "card_w": 900, "card_y": 0.45,
                   "bg": "blur", "float": 3, "z0": 1.0, "z1": 1.2, "trans": "whip"}],
        "overlays": [{"type": "counter", "at": "two", "until": "end", "from": 0, "to": 18, "suffix": "%", "y": 600, "size": 200, "dur": 0.8}],
        "sfx": [{"at": "hook", "file": "sfx/s-hit.wav", "gain": -8}, {"at": "two", "file": "sfx/s-whoosh.wav", "gain": -10}],
        "meta": {"titles": ["A", "B"], "description": "Facts.", "hashtags": ["#shorts"], "tags": ["x", "y"],
                 "pinned_comment": "Q?", "sources": ["src 1"]},
    }
    (d / "spec.yaml").write_text(yaml.safe_dump(spec))
    return d


def test_render_preview_and_motion(project):
    out = footage_render.render(project, preview=True)
    srt = (project / "out/captions.srt").read_text()
    assert out.exists() and "-->" in srt and "One two three four" in srt         # grouped caption lines for upload
    r = subprocess.run([FF, "-i", str(out)], capture_output=True, text=True).stderr
    assert "540x960" in r and "Audio" in r
    dur = float(r.split("Duration: ")[1].split(",")[0].split(":")[-1])
    assert 2.6 <= dur <= 3.0
    win = footage_qa.motion(out)
    assert len(win) >= 5 and max(win) > 1.0                      # a pushing, cutting video moves


def test_post_texts(project):
    footage_package.texts(project)
    o = project / "out"
    assert (o / "titles.txt").read_text() == "1. A\n2. B\n"
    assert (o / "post.txt").read_text().startswith("A\n\nFacts.\n\n#shorts")
    assert (o / "tags.txt").read_text().strip() == "x, y" and (o / "caption.txt").read_text().strip() == "Q?"


def test_voice_sample_is_bundled():
    from footage_voice import SKILL
    f = SKILL / "assets/voices/fish-calm-storyteller.mp3"
    assert f.exists() and f.stat().st_size > 50_000
