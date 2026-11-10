"""Loop ending, SFX audibility, Internet Archive photos, yt-dlp robustness."""
import subprocess
import sys
import types

import numpy as np
import pytest

import assets
import fvcore
import qa
import render
import youtube
from test_tools import mock_urlopen


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "brief.yaml").write_text("title: t\n", encoding="utf-8")
    return tmp_path


def _clip(path, color_a, color_b=None, secs=1.0):
    """A 1 s test video: colour_a (and, when given, colour_b for the last 0.5 s)."""
    ff = fvcore.ffmpeg_bin()
    if color_b is None:
        src = ["-f", "lavfi", "-i", f"testsrc2=s=160x90:r=10:d={secs}" if color_a == "testsrc" else f"color=c={color_a}:s=160x90:r=10:d={secs}"]
        subprocess.run([ff, "-y", "-v", "error", *src, "-pix_fmt", "yuv420p", str(path)], check=True)
    else:
        subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color_a}:s=160x90:r=10:d=0.5", "-f", "lavfi", "-i", f"color=c={color_b}:s=160x90:r=10:d=0.5",
                        "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


# ------------------------------------------------------------------ loop ending
def test_loop_ending_passes_when_last_frame_equals_first(tmp_path):
    v = _clip(tmp_path / "same.mp4", "blue")
    r = qa.loop_ending(v, {"voice_lines": [{"say": "Nobody tells you this, and"}, {"say": "that is why it works, because"}]}, "loop")
    assert r["status"] == "PASS", r


def test_loop_ending_warns_when_last_frame_differs(tmp_path):
    v = _clip(tmp_path / "diff.mp4", "black", "white")
    r = qa.loop_ending(v, {"voice_lines": [{"say": "a, and"}, {"say": "b, so"}]}, "loop")
    assert r["status"] == "WARN" and "does not match the first" in r["detail"]


def test_loop_ending_warns_on_a_closed_last_line(tmp_path):
    v = _clip(tmp_path / "same.mp4", "blue")
    r = qa.loop_ending(v, {"voice_lines": [{"say": "Hook line"}, {"say": "And that is all."}]}, "loop")
    assert r["status"] == "WARN" and "full stop" in r["detail"]
    assert qa.loop_narration([{"say": "x"}, {"say": "and so..."}]) is None


@pytest.mark.parametrize("ending", [None, "cta", "none", "bogus"])
def test_loop_check_is_off_without_ending_loop(tmp_path, ending):
    assert qa.loop_ending(tmp_path / "missing.mp4", {}, ending) is None      # no key: old projects get no row, and no video is even opened


def test_frame_similarity_orders_identical_similar_and_different():
    rng = np.random.default_rng(1)
    a = rng.integers(0, 255, (54, 96)).astype(float)
    same = qa.frame_similarity(a, a)
    assert same["mad"] == 0 and same["ssim"] > 0.99
    assert qa.frame_similarity(a, 255 - a)["ssim"] < 0.1


# ------------------------------------------------------------------ SFX audibility
SR = 22050


def _tone(secs, amp, freq=300):
    t = np.arange(int(secs * SR)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_sfx_cue_check_flags_silent_and_buried_cues_only():
    n = SR * 6
    voice = np.zeros(n, np.float32)
    voice[:] = _tone(6, 0.3)
    sfx = np.zeros(n, np.float32)
    sfx[int(1.0 * SR):int(1.3 * SR)] += _tone(0.3, 0.3, 900)     # audible at 1 s
    sfx[int(3.0 * SR):int(3.3 * SR)] += _tone(0.3, 0.002, 900)   # ~44 dB under the voice at 3 s
    cues = [{"t": 1.0}, {"t": 3.0}, {"t": 5.0}]                  # 5 s: nothing placed
    r = qa.sfx_cue_check(sfx, voice, SR, cues)
    assert r["checked"] == 3 and r["silent"] == [5.0] and [t for t, _ in r["buried"]] == [3.0]


def test_sfx_cue_check_ignores_a_quiet_cue_in_a_gap_between_lines():
    n = SR * 4
    sfx = np.zeros(n, np.float32)
    sfx[SR:SR + 2000] = _tone(2000 / SR, 0.01)
    r = qa.sfx_cue_check(sfx, np.zeros(n, np.float32), SR, [{"t": 1.0}])
    assert r["silent"] == [] and r["buried"] == []


def test_sfx_audibility_reads_stems_and_applies_mix_gains(tmp_path):
    import wave
    def wav(p, x):
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    sr = 48000
    t = np.arange(sr * 4) / sr
    voice = 0.3 * np.sin(2 * np.pi * 300 * t)
    sfx = np.zeros_like(voice)
    sfx[sr:sr + 14400] = 0.003 * np.sin(2 * np.pi * 900 * t[:14400])       # ~40 dB under the voice
    wav(tmp_path / "voice.wav", voice)
    wav(tmp_path / "sfx.wav", sfx)
    r = qa.sfx_audibility(tmp_path, [{"t": 1.0, "type": "pop", "lvl": 2}])
    assert r["status"] == "WARN" and "under the voice" in r["detail"]
    (tmp_path / "mix.json").write_text('{"sfx_gain_db": 30}', encoding="utf-8")        # the mix boosted the SFX: now audible
    assert qa.sfx_audibility(tmp_path, [{"t": 1.0, "type": "pop", "lvl": 2}])["status"] == "PASS"
    assert qa.sfx_audibility(tmp_path, []) is None


def test_mix_json_records_the_gains_qa_needs():
    src = (fvcore.SKILL / "scripts" / "render.py").read_text(encoding="utf-8")
    assert '"voice_gain_db"' in src and '"sfx_gain_db"' in src


# ------------------------------------------------------------------ Internet Archive
ARCHIVE_IMG = {"advancedsearch": {"response": {"docs": [
    {"identifier": "cc0pic", "title": "Lighthouse", "licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/", "creator": "Jo"},
    {"identifier": "bypic", "title": "Pier", "licenseurl": "http://creativecommons.org/licenses/by/4.0/"},
    {"identifier": "ncpic", "title": "NC", "licenseurl": "https://creativecommons.org/licenses/by-nc-sa/4.0/"},
    {"identifier": "pdold", "title": "Old PD", "licenseurl": "http://creativecommons.org/licenses/publicdomain/"},
    {"identifier": "nolic", "title": "None"}]}}}


def test_archive_photos_keep_only_confirmed_licences_and_never_nc(monkeypatch, proj):
    seen = []
    mock_urlopen(monkeypatch, ARCHIVE_IMG, seen)
    res = assets.search_providers("lighthouse", "photo", ["archive"], 5)
    ids = {r["id"]: r for r in res}
    assert set(ids) == {"archive-cc0pic", "archive-bypic", "archive-pdold"}
    assert ids["archive-cc0pic"]["license"] == "CC0" and ids["archive-bypic"]["attribution_required"] is True
    q = next(u for u, *_ in seen if "advancedsearch" in u)
    assert "mediatype%3Aimage" in q and "creativecommons.org" in q          # asks the API for licensed images only
    assert "archive" in assets.DEFAULT_PROVIDERS["photo"] and "archive" in assets.SOURCE_PROVIDERS


def test_archive_photo_download_logs_credit(monkeypatch, proj):
    mock_urlopen(monkeypatch, {**ARCHIVE_IMG,
                               "/metadata/cc0pic": {"files": [{"name": "__ia_thumb.jpg", "format": "Item Tile", "size": "900"},
                                                              {"name": "small.jpg", "format": "JPEG", "size": "4000"},
                                                              {"name": "big.jpg", "format": "JPEG", "size": "90000"},
                                                              {"name": "huge.jpg", "format": "JPEG", "size": str(50 << 20)}]},
                               "/download/cc0pic/big.jpg": b"\xff\xd8\xff\xe0jpeg"})
    monkeypatch.setattr(assets, "limit_size", lambda *a, **k: None)
    res = assets.search(proj, "lighthouse", "photo", ["archive"], 5, False)
    got = assets.get(proj, ["archive-cc0pic"])
    assert got and got[0].name == "archive-cc0pic.jpg"
    cr = {c["id"]: c for c in assets.load_credits(proj)}["archive-cc0pic"]
    assert cr["provider"] == "archive" and cr["license"] == "CC0" and cr["author"] == "Jo" and "Internet Archive" in cr["credit"]


# ------------------------------------------------------------------ yt-dlp
def _fake_ytdlp(monkeypatch, calls):
    class YDL:
        def __init__(self, opts): calls.append(opts)
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=True):
            return {"id": "x", "title": "t", "uploader": "u", "duration": 1, "webpage_url": url, "license": None}
    mod = types.SimpleNamespace(YoutubeDL=YDL)
    monkeypatch.setitem(sys.modules, "yt_dlp", mod)


def test_every_ytdlp_call_gets_the_skills_ffmpeg(monkeypatch, tmp_path):
    calls = []
    _fake_ytdlp(monkeypatch, calls)
    import reference
    try:
        reference.download("https://youtu.be/x", tmp_path)
    except fvcore.FishError:
        pass                                                    # no video file written by the fake
    want = str(__import__("pathlib").Path(fvcore.ffmpeg_bin()).parent)
    assert calls[-1]["ffmpeg_location"] == want
    assert youtube._base_opts()["ffmpeg_location"] == want


def test_subtitle_fetch_retries_429_with_backoff(monkeypatch):
    calls, sleeps = [], []
    class YDL:
        def __init__(self, opts): self.o = opts
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=True):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("HTTP Error 429: Too Many Requests")
            import re
            d = str(self.o["outtmpl"]).rsplit("/", 1)[0]
            open(f"{d}/x.en.vtt", "w").write("WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHello there friends.\n")
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=YDL))
    monkeypatch.setattr(youtube.time, "sleep", lambda s: sleeps.append(s))
    r = youtube.subs("https://youtu.be/x")
    assert len(calls) == 3 and sleeps == [2, 4] and r["text"] == "Hello there friends."


def test_trends_topic_ignores_the_untitled_placeholder():
    import trends
    assert trends.topic_of({"title": "Untitled video", "prompt": "What if AI had emotions?"}) == "What if AI had emotions?"
    assert trends.topic_of({"title": "Real title", "prompt": "x"}) == "Real title"


def test_trends_keeps_acronyms_and_matches_whole_words():
    import trends
    ws = trends._words("What if AI had emotions?")
    assert "ai" in ws and "emotions" in ws
    assert trends._mentions("is ai alive", "ai") and not trends._mentions("she said so", "ai")
    assert trends._mentions("emotional robot", "emotion")
