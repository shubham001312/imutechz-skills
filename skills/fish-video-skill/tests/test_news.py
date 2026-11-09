"""Offline tests for 2.6: the news-short recipe, the newsstory scene checks, meme stickers in memes lint,
the one-browser render fallback and the Creative Commons search filter. No network, no browser."""
import json
import subprocess
from pathlib import Path

import pytest
import yaml

import fvnet
import memes
import recipes
import render
import storyboard
import youtube
from fvcore import FishError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "brief.yaml").write_text(yaml.safe_dump({"title": "t", "memes": {"policy": "viral"}}), encoding="utf-8")
    return tmp_path


def scene(params, sid="n1"):
    return {"id": sid, "type": "newsstory", "say": "Same show. Same premiere.", "params": params}


def check(*scenes):
    return storyboard.validate({"title": "t", "scenes": list(scenes)})


# ------------------------------------------------------------------ recipe
def test_news_short_recipe_is_short_and_uses_newsstory():
    r = recipes.get("news-short")
    assert r["length"] <= 25 and r["platforms"] == ["shorts"]
    sb = recipes.storyboard("news-short")
    assert sb["scenes"] and all(s["type"] == "newsstory" for s in sb["scenes"])
    p = sb["scenes"][0]["params"]
    assert p["slides"][0]["label"].startswith("TODO") and p["fx"][0]["kind"] == "meme"
    assert recipes.brief_over("news-short")["theme"] in r["themes"]


def test_newsstory_is_a_known_scene_type():
    assert "newsstory" in storyboard.SCENE_TYPES
    html = (ROOT / "scripts" / "stage" / "index.html").read_text(encoding="utf-8")
    assert "scenes/newsstory.js" in html


def test_newsstory_scene_parses_as_javascript():
    js = ROOT / "scripts" / "stage" / "scenes" / "newsstory.js"
    r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ------------------------------------------------------------------ storyboard checks
def test_newsstory_needs_slides_and_known_fx():
    errors, _ = check(scene({"fx": [{"kind": "sparkle"}]}))
    assert any("needs `slides`" in e for e in errors)
    assert any("fx kind 'sparkle'" in e for e in errors)


def test_newsstory_paths_stay_inside_the_project():
    errors, _ = check(scene({"slides": [{"src": "../secret.jpg", "label": "x"}], "fx": [{"kind": "meme", "src": "/etc/x.png"}]}))
    assert sum("inside the project" in e for e in errors) == 2


def test_newsstory_warns_on_missing_label_low_fx_and_emoji_only():
    _, warns = check(scene({"slides": [{"src": "assets/photo/a.jpg"}], "fx": [{"kind": "emoji", "e": "x", "y": 0.8}]}))
    assert any("no `label`" in w for w in warns)
    assert any("burned-in captions" in w for w in warns)
    assert any("real reaction meme" in w for w in warns)


def test_a_clean_newsstory_passes():
    errors, warns = check(scene({"slides": [{"src": "assets/photo/a.jpg", "label": "A PERSON, TIFF 2024"},
                                            {"mode": "split", "src": "assets/photo/a.jpg", "src2": "assets/photo/b.jpg", "mystery": True}],
                                 "fx": [{"kind": "meme", "src": "assets/meme/m.png", "y": 0.4}, {"kind": "stamp", "text": "FEUD?", "y": 0.56}]}))
    assert not [e for e in errors if "newsstory" in e or "fx" in e or "slide" in e]
    assert not [w for w in warns if "n1" in w]


def test_footage_slides_get_frames_from_meta(tmp_path):
    d = tmp_path / "build" / "clips" / "c1"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"frames": 180, "fps": 30}), encoding="utf-8")
    p = storyboard._newsstory_params(tmp_path, {"slides": [{"clip": "c1"}, {"clip": "c1", "frames": 12}, {"src": "a.jpg"}]})
    assert p["slides"][0]["frames"] == 180 and p["slides"][0]["fps"] == 30
    assert p["slides"][1]["frames"] == 12                      # an explicit value wins
    assert "frames" not in p["slides"][2]


# ------------------------------------------------------------------ memes lint
def write_sb(proj, scenes):
    (proj / "storyboard.yaml").write_text(yaml.safe_dump({"title": "t", "scenes": scenes}), encoding="utf-8")


def test_meme_sticker_without_credit_fails_and_repeat_warns(proj):
    (proj / "assets" / "meme").mkdir(parents=True)
    (proj / "assets" / "meme" / "m.png").write_bytes(b"x")
    write_sb(proj, [scene({"slides": [{"src": "a.jpg"}], "fx": [{"kind": "meme", "src": "assets/meme/m.png"}]}, "n1"),
                    scene({"slides": [{"src": "a.jpg"}], "fx": [{"kind": "meme", "src": "assets/meme/m.png"}]}, "n2"),
                    scene({"slides": [{"src": "a.jpg"}], "fx": [{"kind": "meme", "src": "assets/meme/gone.png"}]}, "n3")])
    found = memes.lint(proj)
    assert any(f["level"] == "FAIL" and "no credit record" in f["msg"] for f in found)
    assert any(f["level"] == "FAIL" and "missing" in f["msg"] and f["scene"] == "n3" for f in found)
    assert any(f["level"] == "WARN" and "same meme sticker" in f["msg"] and f["scene"] == "n2" for f in found)


def test_meme_sticker_with_credit_is_clean(proj):
    (proj / "assets" / "meme").mkdir(parents=True)
    (proj / "assets" / "meme" / "m.png").write_bytes(b"x")
    fvnet.add_credit(proj, {"provider": "local", "id": "m", "file": "assets/meme/m.png", "license": "CC0", "tier": "safe"})
    write_sb(proj, [scene({"slides": [{"src": "a.jpg"}], "fx": [{"kind": "meme", "src": "assets/meme/m.png"}]})])
    assert memes.lint(proj) == []


# ------------------------------------------------------------------ render fallback
def test_frames_retry_with_one_browser(monkeypatch):
    calls = []

    def fake_node(script, *args, capture=False):
        w = args[list(args).index("--workers") + 1]
        calls.append(w)
        if w != 1:
            raise FishError("command failed (1): frames.mjs ... Unable to capture screenshot")
        return "ok"

    monkeypatch.setattr(render, "node", fake_node)
    assert render._frames(["p", "--platform", "shorts", "--workers", 4], 4, "shorts") == "ok"
    assert calls == [4, 1]


def test_frames_with_one_browser_does_not_retry(monkeypatch):
    monkeypatch.setattr(render, "node", lambda *a, **k: (_ for _ in ()).throw(FishError("boom")))
    with pytest.raises(FishError):
        render._frames(["p", "--workers", 1], 1, "shorts")


# ------------------------------------------------------------------ Creative Commons search
class FakeYDL:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, target, download=False):
        assert "sp=" + youtube.CC_FILTER in target
        return {"entries": [{"id": "a", "title": "A", "channel": "Outlet"}, {"id": "b", "title": "B", "channel": "Reupload"}]}


class FakeYT:
    YoutubeDL = FakeYDL


def test_search_cc_keeps_only_verified_creative_commons(monkeypatch):
    monkeypatch.setattr(youtube, "_ytdlp", lambda: FakeYT)
    lic = {"a": "Creative Commons Attribution license (reuse allowed)", "b": "Standard YouTube License"}
    monkeypatch.setattr(youtube, "info", lambda url: {"license": lic[url.rsplit("=", 1)[-1][-1]], "channel": "X", "channel_is_verified": True})
    out = youtube.search_cc("person interview", 5)
    assert [v["id"] for v in out] == ["a"] and out[0]["channel_verified"] is True
