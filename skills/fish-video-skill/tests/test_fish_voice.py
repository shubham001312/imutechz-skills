"""Offline tests for the fish.audio provider (fishaudio.py + voice.py). The HTTP layer is mocked: no network, no key."""
import io
import json
import struct

import numpy as np
import pytest

import fishaudio
import voice as voicemod
from fvcore import FishError, load_yaml, save_yaml


def wav_bytes(secs=3.0, sr=24000):
    t = np.arange(int(secs * sr)) / sr
    x = (np.sin(2 * np.pi * 120 * t) * 0.3 * (np.sin(2 * np.pi * 3 * t) > -0.9)).astype("<i2" if False else "float32")
    pcm = (x * 32767).astype("<i2").tobytes()
    return b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.fixture
def api(monkeypatch):
    calls = []
    def fake(req, timeout=0):
        h = {k.lower(): v for k, v in req.header_items()}
        calls.append({"url": req.full_url, "headers": h, "data": req.data})
        if req.full_url == fishaudio.MODEL_URL:
            return Resp(json.dumps({"_id": "model123"}).encode())
        return Resp(wav_bytes())
    monkeypatch.setattr(fishaudio.urllib.request, "urlopen", fake)
    monkeypatch.setenv("FISH_API_KEY", "secret-test-key")
    return calls


def test_tts_request_shape(api):
    fishaudio.tts("[calm] Hello there.", {"reference_id": "r1", "model": "s2.1-pro"}, "secret-test-key", 0.9)
    c = api[0]
    body = json.loads(c["data"])
    assert c["url"] == "https://api.fish.audio/v1/tts"
    assert c["headers"]["authorization"] == "Bearer secret-test-key" and c["headers"]["model"] == "s2.1-pro"
    assert body["reference_id"] == "r1" and body["prosody"]["speed"] == 0.9 and body["text"].startswith("[calm]")


def test_missing_key_names_the_variable(monkeypatch, tmp_path):
    monkeypatch.delenv("FISH_API_KEY", raising=False)
    monkeypatch.setattr(fishaudio, "secret", lambda n, p=None: "")
    with pytest.raises(FishError, match="FISH_API_KEY"):
        voicemod.pick_provider({"voice": {"fallback": {}}}, None, "fish")


def test_tags_are_subtle_and_model_aware():
    assert fishaudio.tag_text("Go.", "hook", {}) == "[confident] Go."
    assert fishaudio.tag_text("Go.", None, {}) == "[calm] Go."
    assert fishaudio.tag_text("Go.", "hook", {"model": "s1"}) == "(confident) Go."
    assert fishaudio.tag_text("Go.", "hook", {"emotion": False}) == "Go."


def test_next_speed_closed_loop():
    fc = {"target_wps": 2.7}
    assert fishaudio.next_speed(1.0, 10, 10 / 2.7, fc) is None            # on target
    assert fishaudio.next_speed(1.0, 3, 0.5, fc) is None                  # too short to steer
    assert fishaudio.next_speed(1.0, 10, 10 / 3.5, fc) < 1.0              # too fast: slow down
    assert fishaudio.next_speed(1.0, 10, 10 / 2.0, fc) > 1.0              # too slow: speed up


def test_clone_writes_reference_id_to_brief(api, smoke_project, tmp_path):
    sample = tmp_path / "me.wav"
    sample.write_bytes(wav_bytes())
    with pytest.raises(FishError, match="consent"):
        fishaudio.clone_project(smoke_project, sample, None, False)
    assert fishaudio.clone_project(smoke_project, sample, "T", True) == "model123"
    v = load_yaml(smoke_project / "brief.yaml")["voice"]
    assert v["provider"] == "fish" and v["fish"]["reference_id"] == "model123"
    assert b"multipart" in api[0]["headers"]["content-type"].encode() and b'name="voices"' in api[0]["data"]


def test_synth_line_caches_and_times(api, smoke_project):
    cfg = {"voice": {"language": "en-US", "fish": {"reference_id": "r1", "target_wps": 2.7}}, "pacing": {}}
    out = smoke_project / "build" / "voice" / "fish"
    out.mkdir(parents=True)
    say = "One two three four five six seven eight."
    c1 = voicemod.synth_line(say, "fish", "k", cfg, out, "s1", tag="hook")
    n = len(api)
    c2 = voicemod.synth_line(say, "fish", "k", cfg, out, "s1", tag="hook")
    assert len(api) == n and c1["hash"] == c2["hash"]                      # unchanged line: no new request
    assert c1["words"][0]["text"] == "One" and len(c1["words"]) == 8 and c1["duration"] > 0
    assert json.loads(api[0]["data"])["text"].startswith("[confident] One")
    voicemod.synth_line(say, "fish", "k", cfg, out, "s1", tag="setup")      # a changed tag is a new take
    assert len(api) > n
