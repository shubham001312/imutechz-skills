"""The kinetic-explainer recipe: recipe, theme, scene registration, gates, logo resolution, and a deterministic render."""
import hashlib
import json
import subprocess
import sys

import pytest

import gates
import recipes
import storyboard as sbm
import themes
from conftest import ROOT

PY = sys.executable
CLI = str(ROOT / "scripts" / "fishvideo.py")


def test_kinetic_recipe_loads_and_is_a_sub_30_second_short():
    r = recipes.get("kinetic-explainer")
    assert r["platforms"] == ["shorts"] and r["length"] < 30 and r["long_form_ok"] is True
    assert r["theme"] == "insider-light" and r["theme"] in r["themes"] and all(t in themes.all_themes() for t in r["themes"])
    assert r["gate"] and r["assets"] and r["beats"]
    b = recipes.brief_over("kinetic-explainer")
    assert b["captions"]["burn"] is False and b["sfx"] == "rich" and b["length"] == r["length"]


def test_kinetic_beats_scale_with_the_chosen_length_and_cta_is_optional():
    r = recipes.get("kinetic-explainer")
    ids = lambda n: [b["id"] for b in recipes.expand(r, n)]
    assert ids(28) == ["hook", "name", "point1", "point2", "payoff"]            # default Short: 2 points, no CTA in the skeleton
    assert [i for i in ids(75) if i.startswith("point")] == [f"point{n}" for n in range(1, 6)]
    assert [i for i in ids(45) if i.startswith("point")] == ["point1", "point2", "point3"]
    assert ids(28) == [b["id"] for b in recipes.expand(r)]
    assert recipes.expand(r, 28, optional=True)[-1]["id"] == "cta"
    assert recipes.points_for_length(recipes.get("roadmap-explainer"), 60) == 5   # recipes without a `points:` rule keep `steps`
    sb = recipes.storyboard("kinetic-explainer", 75)
    assert {s["type"] for s in sb["scenes"]} == {"kstack"} and "point5" in [s["id"] for s in sb["scenes"]]
    assert "cta" in recipes.asset_plan("kinetic-explainer") and "(optional)" in recipes.asset_plan("kinetic-explainer")


def test_insider_light_is_a_light_one_accent_theme():
    t = themes.get("insider-light")
    assert t["mode"] == "light" and t["colors"]["bg"].lower() in ("#f2f2f2", "#f3f3f3") and t["captions"]["style"] == "none"
    assert t["motion"]["blur_cut"] > 0


def test_kstack_is_registered_everywhere_a_scene_must_be():
    assert "kstack" in sbm.SCENE_TYPES
    stage = ROOT / "scripts" / "stage"
    assert "scenes/kinetic.js" in (stage / "index.html").read_text()
    js = (stage / "scenes" / "kinetic.js").read_text()
    assert "S.kstack" in js
    for banned in ("Math.random", "Date.now", "new Date", "requestAnimationFrame", "@keyframes", "transition:"):
        assert banned not in js, banned


def test_kstack_without_an_element_counts_as_text_and_with_one_as_graphic_or_image():
    kind = lambda params: gates.classify({"id": "x", "type": "kstack", "params": params})[0]
    assert kind({"lines": ["a"]}) == "text"
    assert kind({"lines": ["a"], "element": "none"}) == "text"
    assert kind({"lines": ["a"], "element": "pill", "pill": {"name": "X"}}) == "graphic"
    assert kind({"lines": ["a"], "element": "card", "card": {"src": "assets/shots/a.png"}}) == "image"


def test_kstack_logo_slugs_resolve_to_paths(monkeypatch):
    import thumbs
    monkeypatch.setattr(thumbs, "resolve_logos", lambda items: [{"slug": items[0], "title": "T", "hex": "112233", "d": "M0 0h24v24H0z", "tile": "#ffffff"}])
    out = sbm._kstack_params({"pill": {"name": "T", "logo": {"slug": "t"}}, "orbit": {"center": {"slug": "c"}, "items": [{"slug": "a"}, {"glyph": "x"}]}})
    assert out["pill"]["logo"]["d"].startswith("M0") and out["orbit"]["items"][0]["hex"] == "112233" and out["orbit"]["items"][1] == {"glyph": "x"}


@pytest.mark.e2e
def test_kstack_stills_render_deterministically(tmp_path):
    from PIL import Image, ImageDraw
    import brief
    p = brief.new_project(tmp_path / "k", "x", **recipes.brief_over("kinetic-explainer"))
    (p / "assets" / "own").mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (800, 530), "#101216"); ImageDraw.Draw(im).rectangle([40, 40, 500, 70], fill="#4ec9b0"); im.save(p / "assets" / "own" / "s.png")
    sb = {"title": "t", "bpm": 120, "style": "studio-kinetic", "texture": None, "background": "plain", "vignette": False, "scenes": [
        {"id": "hook", "type": "kstack", "transition": "cut", "say": ["Free. Local. Private."], "params": {"lines": ["**Free.**", "**Local.**", "==Private.=="]}},
        {"id": "p1", "type": "kstack", "transition": "cut", "say": ["First, one command."], "params": {"number": "First", "lines": ["one **command**"], "element": "card", "card": {"src": "assets/own/s.png"}}},
        {"id": "p2", "type": "kstack", "transition": "cut", "say": ["Second, it plugs in."], "params": {"number": "Second", "lines": ["it **plugs** in"], "element": "orbit", "orbit": {"center": {"glyph": "O"}, "items": [{"glyph": "A"}, {"glyph": "B"}, {"glyph": "C"}, {"glyph": "D"}, {"glyph": "E"}]}}}]}
    import yaml
    (p / "storyboard.yaml").write_text(yaml.safe_dump(sb), encoding="utf-8")
    shots = []
    for _ in range(2):
        r = subprocess.run([PY, CLI, "stills", str(p), "--at", "0.4,2.0,3.5"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, r.stderr[-1500:]
        out = json.loads(r.stdout.strip().splitlines()[-1])
        assert out["errors"] == 0 and len(out["stills"]) == 3
        shots.append([Image.open(f).convert("L") for f in out["stills"]])
    # Same input, same picture. Under heavy CPU load Chromium's image resampling can move a few pixels inside an image
    # card by up to ~9/255 (measured 2026-11-10; seen only when several stills are taken in one session), so compare
    # with a tight tolerance: any real change in what the scene draws is far larger than this.
    from PIL import ImageChops, ImageStat
    for a_, b_ in zip(shots[0], shots[1]):
        d = ImageChops.difference(a_, b_)
        assert ImageStat.Stat(d).mean[0] < 0.25 and d.getextrema()[1] <= 16
    first = shots[0]
    assert all(ImageStat.Stat(ImageChops.difference(first[i], first[j])).mean[0] > 2 for i in range(3) for j in range(i + 1, 3))
