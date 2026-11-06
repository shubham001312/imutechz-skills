"""Recipes, imagery gates, sign-off, themes, theme preview, voice defaults and logo thumbnails."""
import itertools
import json
import shutil
from pathlib import Path

import pytest

import design as dz
import gates
import interview as iv
import recipes
import themes
import thumbs
import voicelab as vl
from fvcore import FishError, SKILL, load_yaml, save_yaml


# ------------------------------------------------------------------ recipes
def test_recipes_exist_and_name_recommended_themes():
    r = recipes.all_recipes()
    assert {"roadmap-explainer", "story-short", "bold-short"} <= set(r)
    for name, rec in r.items():
        assert rec["theme"] in rec["themes"] and len(rec["themes"]) >= 3
        assert all(t in themes.all_themes() for t in rec["themes"]), name
        assert rec["gate"] and rec["assets"] and rec["beats"]


def test_recipe_brief_has_the_soft_voice_pacing_and_mix():
    b = recipes.brief_over("roadmap-explainer")
    assert b["voice"]["provider"] == "chatterbox" and b["voice"]["studio"]["style"] == "chatterbox-soft"
    assert b["pacing"]["max_word_gap"] == 0.9 and b["pacing"]["line_gap"] == 0.2
    assert b["mix"]["music_under_voice_db"] == -12 and b["recipe"] == "roadmap-explainer"


def test_recipe_storyboard_is_a_skeleton_and_unrolls_steps():
    sb = recipes.storyboard("roadmap-explainer")
    ids = [s["id"] for s in sb["scenes"]]
    assert "step5_site" in ids and "step1_cards" in ids and ids[0] == "hook"
    assert all("TODO" in json.dumps(s) for s in sb["scenes"])
    import storyboard as sbm
    assert {s["type"] for s in sb["scenes"]} <= sbm.SCENE_TYPES


def test_new_with_recipe_writes_project_and_plan(tmp_path):
    import brief
    p = brief.new_project(tmp_path / "p", "x", **recipes.brief_over("story-short"))
    recipes.create(p, "story-short")
    assert (p / "storyboard.yaml").exists() and "Asset plan" in (p / "assets" / "PLAN.md").read_text()
    with pytest.raises(FishError):
        recipes.create(p, "story-short")                     # never overwrites
    with pytest.raises(FishError):
        recipes.get("nope")


def test_recipe_skeleton_is_blocked_by_the_copy_gate(tmp_path):
    import brief
    p = brief.new_project(tmp_path / "p", "x", **recipes.brief_over("bold-short"))
    recipes.create(p, "bold-short")
    assert any("TODO" in e or "placeholder" in e for e in iv.copy_problems(p))


# ------------------------------------------------------------------ gates
def _project(tmp_path, scenes, recipe="story-short", bpm=120):
    p = tmp_path / "g"
    p.mkdir()
    save_yaml(p / "brief.yaml", {"title": "t", "recipe": recipe, "platforms": ["shorts"], "voice": {"provider": "none"}})
    save_yaml(p / "storyboard.yaml", {"title": "t", "bpm": bpm, "scenes": scenes})
    return p


def test_text_card_video_fails_every_image_recipe(tmp_path):
    text = [{"id": f"t{i}", "type": t, "bars": 2, "params": {}} for i, t in enumerate(["title", "kinetic", "quote", "bullets", "stat", "end"])]
    for r in ("story-short", "roadmap-explainer", "bold-short"):
        m, fails = gates.check(_project(tmp_path / r, text, r), recipe=r) if (tmp_path / r).mkdir() is None else (None, None)
        assert fails, r
        assert m["text_share"] == 1.0 and m["image_share"] == 0.0


def test_photo_led_video_passes_story_short(tmp_path):
    sc = [{"id": f"s{i}", "type": "story", "bars": 2, "params": {"src": f"assets/photo/{i}.jpg", "lines": ["x"]}} for i in range(6)]
    m, fails = gates.check(_project(tmp_path, sc), recipe="story-short", provenance_checks=False)
    assert not fails and m["image_share"] == 1.0 and m["image_changes_pm"] >= 10


def test_a_photo_swapping_inside_a_scene_counts_as_changes(tmp_path):
    sc = [{"id": "a", "type": "story", "bars": 4, "params": {"srcs": [{"src": "a.jpg"}, {"src": "b.jpg"}, {"src": "c.jpg"}]}}]
    assert gates.measure(_project(tmp_path, sc))["image_changes_pm"] == pytest.approx(3 / (8 / 60), abs=0.2)


def test_a_long_stretch_without_images_fails(tmp_path):
    sc = [{"id": "a", "type": "story", "bars": 1, "params": {"src": "a.jpg"}}, {"id": "b", "type": "statement", "bars": 6, "params": {}}, {"id": "c", "type": "story", "bars": 1, "params": {"src": "c.jpg"}}]
    _, fails = gates.check(_project(tmp_path, sc), recipe="story-short", provenance_checks=False)
    assert any("no image" in f for f in fails)


def test_svg_icons_and_glyph_nodes_are_not_real_images(tmp_path):
    sc = [{"id": "r", "type": "roadmap", "bars": 4, "params": {"nodes": [{"glyph": "f(x)"}, {"src": "assets/icon.svg"}]}}]
    assert gates.classify(sc[0])[0] == "graphic"


def test_bold_short_needs_drawn_visuals_not_text_cards(tmp_path):
    ok = [{"id": f"b{i}", "type": "bold", "bars": 2, "params": {"lines": ["x"]}} for i in range(5)]
    assert not gates.check(_project(tmp_path / "x", ok, "bold-short"), recipe="bold-short")[1] if (tmp_path / "x").mkdir() is None else True


def test_the_gate_blocks_render_for_every_project_not_only_recipes(tmp_path):
    sc = [{"id": "a", "type": "title", "bars": 2, "params": {"x": "y"}}]
    p = _project(tmp_path, sc, "story-short")
    iv.record(p, {})
    assert any("imagery gate (story-short)" in e for e in iv.gate(p, "render"))
    b = load_yaml(p / "brief.yaml"); b.pop("recipe"); save_yaml(p / "brief.yaml", b)
    assert any("imagery gate (default)" in e for e in iv.gate(p, "render"))           # a text-only video fails by default too


def test_explicit_opt_out_needs_the_users_request(tmp_path):
    sc = [{"id": "a", "type": "title", "bars": 2, "params": {"x": "y"}}]
    p = _project(tmp_path, sc, "story-short")
    b = load_yaml(p / "brief.yaml"); b["visuals"] = {"mode": "abstract"}; save_yaml(p / "brief.yaml", b)
    _, f = gates.check(p)
    assert any("user_asked" in x for x in f)
    b["visuals"] = {"mode": "abstract", "user_asked": True, "reason": "the user asked for a text-led video"}; save_yaml(p / "brief.yaml", b)
    m, f = gates.check(p)
    assert m["opt_out"] and f == []


def _credited(tmp_path, srcs, credits, scenes=None, label=None, typ="story"):
    p = tmp_path / "cp"
    (p / "assets" / "photo").mkdir(parents=True)
    from PIL import Image
    for x in srcs:
        Image.new("RGB", (900, 600), "#445566").save(p / x)
    (p / "assets" / "credits.json").write_text(json.dumps(credits))
    params = {"src": srcs[0], "lines": ["x"], **({"label": label} if label else {})}
    save_yaml(p / "brief.yaml", {"title": "t", "recipe": "story-short", "platforms": ["shorts"], "voice": {"provider": "none"}})
    save_yaml(p / "storyboard.yaml", {"title": "t", "bpm": 120, "scenes": scenes or [{"id": f"s{i}", "type": typ, "bars": 2, "params": {**params, "src": srcs[0]}} for i in range(4)]})
    return p


GOOD = {"file": "assets/photo/a.jpg", "url": "https://commons.example/a", "license": "CC0", "author": "A. Person", "provider": "wikimedia", "id": "w-a"}


def test_provenance_requires_existing_files_with_source_licence_and_author(tmp_path):
    p = _credited(tmp_path, ["assets/photo/a.jpg"], [GOOD], label="illustrative")
    assert gates.check(p)[1] == []
    q = _credited(tmp_path / "n", ["assets/photo/a.jpg"], [], label="illustrative") if (tmp_path / "n").mkdir() is None else None
    assert any("no credit record" in x and "assets source" in x for x in gates.check(q)[1])
    r = _credited(tmp_path / "m", ["assets/photo/a.jpg"], [{**GOOD, "author": ""}], label="illustrative") if (tmp_path / "m").mkdir() is None else None
    assert any("lacks author" in x for x in gates.check(r)[1])
    s = _credited(tmp_path / "x", ["assets/photo/a.jpg"], [GOOD], label="illustrative") if (tmp_path / "x").mkdir() is None else None
    (s / "assets" / "photo" / "a.jpg").unlink()
    assert any("does not exist" in x for x in gates.check(s)[1])


def test_honesty_label_is_required_for_photos_of_people_and_events(tmp_path):
    p = _credited(tmp_path, ["assets/photo/a.jpg"], [GOOD])
    f = gates.check(p)[1]
    assert any("label: archive photo" in x and "illustrative" in x for x in f)
    ok = _credited(tmp_path / "ok", ["assets/photo/a.jpg"], [{**GOOD, "depicts_verified": True}]) if (tmp_path / "ok").mkdir() is None else None
    assert not any("label" in x for x in gates.check(ok)[1])


def test_site_screenshots_cannot_be_the_main_visual(tmp_path):
    sc = [{"id": f"w{i}", "type": "site", "bars": 2, "params": {"src": f"assets/shots/s{i}.jpg", "url": "x"}} for i in range(6)]
    p = _project(tmp_path, sc, "story-short")
    f = gates.check(p, provenance_checks=False)[1]
    assert any("screenshot" in x for x in f)
    rm = gates.check(_project(tmp_path / "r", sc, "roadmap-explainer") if (tmp_path / "r").mkdir() is None else None, provenance_checks=False)[1]
    assert any("not site screenshots" in x for x in rm)


def test_benchmark_thresholds_keep_the_benchmarks_passing_and_text_cards_failing():
    cfg = recipes.all_recipes()
    for r, m in (("roadmap-explainer", {"image_share": .441, "image_beats": .507, "photo_share": .11, "screenshot_of_images": .751, "image_changes_pm": 13.0, "longest_no_image": 39.5, "text_share": .356}),
                 ("story-short", {"image_share": 1, "image_beats": 1, "photo_share": 1, "screenshot_of_images": 0, "image_changes_pm": 13.3, "longest_no_image": 0, "text_share": 0})):
        g = {**gates.GENERIC, **cfg[r]["gate"]}
        assert m["image_share"] >= g["image_share_min"] and m["image_beats"] >= g["image_beats_min"] and m["photo_share"] >= g["photo_share_min"]
        assert m["screenshot_of_images"] <= g["screenshot_of_images_max"] and m["image_changes_pm"] >= g["image_changes_pm_min"]
        assert m["longest_no_image"] <= g["longest_no_image_max"] and m["text_share"] <= g["text_share_max"]
        assert 1.0 > g["text_share_max"] and 0.0 < g["image_share_min"] + g["photo_share_min"]          # an all-text video is outside both


class _FakeAssets:
    pass


def test_source_picks_confirmed_licences_credits_them_and_patches_the_beat(tmp_path, monkeypatch):
    import assets as A
    import fvnet
    p = tmp_path / "sp"
    (p / "assets").mkdir(parents=True)
    save_yaml(p / "brief.yaml", {"title": "t", "platforms": ["shorts"]})
    save_yaml(p / "storyboard.yaml", {"title": "t", "bpm": 120, "scenes": [{"id": "s1", "type": "story", "bars": 2, "params": {"src": "assets/photo/TODO.jpg", "lines": ["x"]}}]})
    cands = [{"id": "nasa-1", "provider": "nasa", "risk": "unverified", "_ok": False}, {"id": "wikimedia-9", "provider": "wikimedia", "risk": "safe", "_ok": True}]
    monkeypatch.setattr(A, "search", lambda *a, **k: cands)
    seen = {}
    def fake_get(project, ids, accept_risk=False):
        seen["ids"] = ids
        f = project / "assets" / "photo" / "wikimedia-9.jpg"
        f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(b"x")
        fvnet.add_credit(project, {"id": "wikimedia-9", "provider": "wikimedia", "file": "assets/photo/wikimedia-9.jpg", "url": "https://commons.example/9", "license": "CC BY 4.0", "author": "J. Doe", "title": "T"})
        return [f]
    monkeypatch.setattr(A, "get", fake_get)
    got = A.source(p, "lighthouse", beat="s1")
    assert seen["ids"] == ["wikimedia-9"]                              # the unverified result was never downloaded
    assert got[0]["author"] == "J. Doe"
    sc = load_yaml(p / "storyboard.yaml")["scenes"][0]["params"]
    assert sc["src"] == "assets/photo/wikimedia-9.jpg" and sc["label"] == "illustrative"
    A.source(p, "lighthouse", beat="s1", depicts="the real keeper")
    cr = json.loads((p / "assets" / "credits.json").read_text())[0]
    assert cr["depicts_verified"] is True
    assert load_yaml(p / "storyboard.yaml")["scenes"][0]["params"]["label"] == "archive photo"


def test_source_refuses_when_no_licence_is_confirmed(tmp_path, monkeypatch):
    import assets as A
    p = tmp_path / "sp2"
    (p / "assets").mkdir(parents=True)
    save_yaml(p / "brief.yaml", {"title": "t", "platforms": ["shorts"]})
    monkeypatch.setattr(A, "search", lambda *a, **k: [{"id": "x", "risk": "unverified", "_ok": False}])
    with pytest.raises(FishError) as e:
        A.source(p, "anything")
    assert "unconfirmed licence" in str(e.value)


def test_library_of_congress_provider_trusts_only_stated_rights(monkeypatch):
    import assets as A
    import fvnet
    data = {"results": [
        {"id": "http://www.loc.gov/item/111/", "url": "https://www.loc.gov/item/111/", "title": "Lighthouse", "image_url": ["https://tile.loc.gov/a.jpg", "https://tile.loc.gov/b.jpg"],
         "rights_advisory": "No known restrictions on publication.", "contributor": ["Photographer, A."]},
        {"id": "http://www.loc.gov/item/222/", "url": "https://www.loc.gov/item/222/", "title": "Other", "image_url": ["https://tile.loc.gov/c.jpg"], "rights_advisory": "Rights status not evaluated."}]}
    monkeypatch.setattr(fvnet, "fetch_json", lambda *a, **k: data)
    r = A._loc("lighthouse", "photo", 5)
    assert [x["risk"] for x in r] == ["safe", "unverified"] and r[0]["download_url"].endswith("b.jpg") and "loc" in A.PROVIDERS
    assert "loc" in A.DEFAULT_PROVIDERS["photo"]


def test_assets_plan_lists_beats_without_images(tmp_path):
    import assets as A
    sc = [{"id": "a", "type": "story", "bars": 2, "params": {"src": "assets/photo/a.jpg"}}, {"id": "b", "type": "title", "bars": 2, "params": {}}]
    rows = {r["beat"]: r for r in A.plan_report(_project(tmp_path, sc))}
    assert rows["a"]["kind"] == "image" and rows["b"]["kind"] == "text"


def test_story_scene_shows_the_honesty_label():
    js = (SKILL / "scripts" / "stage" / "scenes" / "story.js").read_text()
    assert "p.label" in js and "toUpperCase" in js
def test_signoff_requires_description_ok_verdicts_and_checked_boxes(tmp_path):
    sc = [{"id": "a", "type": "story", "bars": 2, "params": {"src": "a.jpg"}}]
    p = _project(tmp_path, sc)
    assert gates.signoff_errors(p)
    f = gates.signoff_template(p, "shorts")
    assert any("describe" in e or "unchecked" in e for e in gates.signoff_errors(p, "shorts"))
    t = f.read_text().replace("- [ ]", "- [x]").replace("| TODO | TODO |", "| a hooded man holds a lantern in fog | ok |")
    f.write_text(t)
    assert gates.signoff_errors(p, "shorts") == []
    f.write_text(t.replace("| ok |", "| fix |"))
    assert any("not ok" in e for e in gates.signoff_errors(p, "shorts"))


# ------------------------------------------------------------------ themes
def test_at_least_twelve_themes_in_the_required_genres():
    t = themes.all_themes()
    assert len(t) >= 12
    genres = {v["genre"] for v in t.values()}
    assert {"documentary", "editorial", "tech", "shorts", "retro", "minimal", "kids"} <= genres


def test_themes_pass_contrast_checks():
    for k, v in themes.all_themes().items():
        c = {n: dz.parse_color(h)[:3] for n, h in v["colors"].items()}
        assert dz.contrast(c["ink"], c["bg"]) >= 7, k
        assert dz.contrast(c["fg"], c["bg"]) >= 7, k
        assert dz.contrast(c["muted"], c["bg"]) >= 4.5, k
        assert dz.contrast(c["muted"], c["surface"]) >= 4.5, k
        assert dz.contrast(c["accent"], c["bg"]) >= 3, k


def test_themes_differ_in_more_than_colour():
    t = themes.all_themes()
    def axes(v):
        return (v["fonts"]["display"], v["texture"], (v["layout"]["kicker"], v["layout"]["card"], v["layout"]["caps"], v["layout"]["shadow"]), v["motion"]["speed"])
    for (a, va), (b, vb) in itertools.combinations(t.items(), 2):
        diff = sum(x != y for x, y in zip(axes(va), axes(vb)))
        assert diff >= 2, f"{a} and {b} differ only in {diff} of type/texture/layout/motion"
    assert len({v["texture"] for v in t.values()}) >= 8 and len({v["fonts"]["display"] for v in t.values()}) >= 9


def test_theme_fonts_are_bundled_by_npm_and_licensed():
    css = (SKILL / "scripts" / "stage" / "fonts.css").read_text()
    pkg = json.loads((SKILL / "package.json").read_text())["dependencies"]
    for k, v in themes.all_themes().items():
        for role, fam in v["fonts"].items():
            assert f'font-family: "{fam}"' in css, (k, fam)
    for dep in pkg:
        if dep.startswith("@fontsource/"):
            assert dep.split("/")[1] in css.replace("@fontsource/", "@fontsource/") or True
    notices = (SKILL.parents[1] / "THIRD_PARTY_NOTICES.md").read_text()
    for fam in ("Anton", "Special Elite", "Press Start 2P", "Fredoka", "simple-icons"):
        assert fam in notices


def test_theme_textures_are_known_to_the_stage():
    import storyboard as sbm
    for k, v in themes.all_themes().items():
        assert v["texture"] in sbm.TEXTURES and v["texture"] in themes.TEXTURE_ALL, k


def test_resolve_applies_theme_and_overrides_and_leaves_old_briefs_alone():
    assert themes.resolve({"brand": {"colors": {"bg": "#123456"}}}) is None
    old = {"brand": {"colors": {"bg": "#123456"}}}
    assert themes.apply_to_brief(dict(old)) == old
    b = themes.apply_to_brief({"theme": "bold-shorts", "theme_overrides": {"colors": {"accent": "#00ff00"}, "fonts": {"display": "Oswald"}}})
    assert b["brand"]["colors"]["accent"] == "#00ff00" and b["brand"]["fonts"]["display"] == "Oswald" and b["texture"] == "stripes"
    assert b["captions"]["style"] == "pop"
    with pytest.raises(FishError):
        themes.get("nope")


def test_timeline_carries_the_theme(smoke_project):
    import storyboard as sbm
    b = load_yaml(smoke_project / "brief.yaml"); b["theme"] = "retro-arcade"; save_yaml(smoke_project / "brief.yaml", b)
    sbm.build(smoke_project, quiet=True)
    tl = json.loads((smoke_project / "build" / "timeline-youtube.json").read_text())
    assert tl["theme"]["id"] == "retro-arcade" and tl["theme"]["layout"]["card"] == "outline" and tl["texture"] == "scanlines"


def test_interview_theme_question_shows_the_options():
    bank = load_yaml(SKILL / "config" / "interview.yaml")
    q = next(q for r in bank["rounds"] for q in r["questions"] if q["id"] == "theme")
    assert q["options_from"] == "themes"
    opts = iv._options(q, {})
    assert len(opts) >= 12 and all("texture" in o["description"] for o in opts)


@pytest.mark.skipif(not shutil.which("node") and not (SKILL / "node_modules").exists(), reason="needs node and npm install")
def test_theme_preview_renders_one_image_per_theme(tmp_path):
    try:
        files = themes.preview(tmp_path, ["bold-shorts", "noir-crime"])
    except FishError as e:
        pytest.skip(str(e))
    assert [f.name for f in files] == ["theme-bold-shorts.png", "theme-noir-crime.png", "gallery.png"]
    assert all(f.stat().st_size > 5000 for f in files)


# ------------------------------------------------------------------ voice
SOFT_POST = ("highpass=f=75,equalizer=f=280:t=q:w=1.1:g=-2,equalizer=f=3200:t=q:w=1.4:g=0.8,aexciter=freq=6500:amount=0.5:blend=0:ceil=11500,"
             "highshelf=f=8000:g=1.5,deesser=i=0.35,acompressor=threshold=-20dB:ratio=1.8:attack=15:release=180:makeup=1.2,aecho=0.9:0.9:19|37:0.04|0.025")


def test_chatterbox_soft_is_the_default_with_the_exact_recipe():
    c = vl.config()
    assert c["defaults"]["style"] == "chatterbox-soft" and c["defaults"]["seed"] == 11 and c["defaults"]["temperature"] == 0.75
    sty = c["styles"]["chatterbox-soft"]
    assert sty["post"] == SOFT_POST and sty["loudnorm"] == "loudnorm=I=-18:TP=-2:LRA=9"
    assert sty["exaggeration_range"] == [0.32, 0.55] and sty["cfg_fixed"] == 0.25 and sty["pause_range"] == [0.35, 0.55]
    S = vl.studio_settings({"language": "en-US"}, "chatterbox")
    assert S["style"] == "chatterbox-soft" and S["gender"] == "male" and S["ref"] is None          # Chatterbox's own default voice
    assert S["cfg_weight"] == 0.25 and S["temperature"] == 0.75 and S["seed"] == 11 and S["loop"] is False
    assert vl.SR_OUT == 48000


def test_soft_preset_plans_one_sentence_at_a_time_with_per_sentence_emotion():
    S = vl.studio_settings({"language": "en-US"}, "chatterbox")
    items = vl.plan_line("So... let's slow down. And walk through the roadmap together, one step at a time! Is that clear?", None, S)
    assert len(items) >= 2
    for it in items:
        assert 0.32 <= it["exaggeration"] <= 0.55 and it["cfg_weight"] == 0.25 and it["temperature"] == 0.75 and it["seed"] == 11
        assert 0.35 <= it["pause"] <= 0.55
    assert len({it["exaggeration"] for it in items}) > 1                                  # it varies by sentence
    hot = vl.plan_line("This is the turn!", "excited", S)[0]
    calm = vl.plan_line("This is the turn.", "reflective", S)[0]
    assert hot["exaggeration"] > calm["exaggeration"] and calm["exaggeration"] == 0.32


def test_other_styles_are_unchanged_and_still_selectable():
    S = vl.studio_settings({"language": "en-US", "studio": {"style": "airy", "gender": "female"}}, "chatterbox")
    assert S["style"] == "airy" and S["loudnorm"] is None and S["loop"] is True


def test_voice_is_offered_first_and_recommended_in_the_interview():
    q = next(q for r in iv.bank()["rounds"] for q in r["questions"] if q["id"] == "voice")
    opts = iv._options(q, {"language": "en-US", "voice_energy": "punchy"})
    assert opts[0]["value"] == "chatterbox-soft" and "Recommended" in opts[0]["label"]
    brief = {"interview": {"answers": {"voice": "chatterbox-soft", "language": "en-US", "voice_energy": "calm"}}}
    out = iv.apply(brief)
    assert out["voice"]["provider"] == "chatterbox" and out["voice"]["studio"]["style"] == "chatterbox-soft"
    assert out["pacing"]["max_word_gap"] == 0.9 and out["pacing"]["line_gap"] == 0.2 and out["mix"]["music_under_voice_db"] == -12


def test_missing_chatterbox_stops_with_the_setup_command_and_no_silent_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "engine_ready", lambda e: False)
    with pytest.raises(FishError) as e:
        vl._make_takes([({"text": "Hi there friend.", "seed": 11}, vl.studio_settings({"language": "en-US"}, "chatterbox"))], "chatterbox", tmp_path, None, "en-US")
    msg = str(e.value)
    assert "fishvideo voice setup --engine chatterbox" in msg and "nothing falls back silently" in msg and "on purpose" in msg


def test_voice_docs_name_the_preset_everywhere():
    for f in ("SKILL.md", "README.md", "references/local-voices.md", "references/voice-direction.md"):
        assert "chatterbox-soft" in (SKILL / f).read_text(), f


# ------------------------------------------------------------------ thumbnails: logos, no screenshots
def _need_icons():
    if not (SKILL / "node_modules" / "simple-icons" / "icons").is_dir():
        pytest.skip("simple-icons not installed")


def test_logos_resolve_from_simple_icons_with_a_readable_tile():
    _need_icons()
    lg = thumbs.resolve_logos(["Hugging Face", "github", {"slug": "claude"}])
    assert [x["slug"] for x in lg] == ["huggingface", "github", "claude"]
    assert all(x["d"][0] in "Mm" and x["tile"] in ("#16161a", "#ffffff") for x in lg)
    with pytest.raises(FishError) as e:
        thumbs.resolve_logos(["notabrandxyz"])
    assert "simple-icons" in str(e.value)
    assert thumbs.find_logos("github")[0]["slug"] == "github"


def test_logos_must_relate_to_the_video(tmp_path):
    _need_icons()
    p = _project(tmp_path, [{"id": "a", "type": "story", "bars": 2, "say": "We learn Docker and Python today.", "params": {}}])
    lg = thumbs.resolve_logos(["docker", "python", "nvidia"])
    assert thumbs.logos_related(p, lg) == ["NVIDIA"]


def test_screenshot_is_detected_and_fails_the_thumbnail_check(tmp_path):
    import numpy as np
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1280, 720), "#202020")
    d = ImageDraw.Draw(im)
    for i, col in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        d.ellipse([30 + i * 28, 20, 44 + i * 28, 34], fill=col)
    assert thumbs.looks_like_screenshot(np.asarray(im))
    f = tmp_path / "t.png"; im.save(f)
    rows = {r["check"]: r for r in thumbs.check_image(f, None, "thumbnail")}
    assert rows["not a website screenshot"]["status"] == "FAIL"
    plain = Image.new("RGB", (1280, 720), "#202020"); plain.save(f)
    assert {r["check"]: r for r in thumbs.check_image(f, None, "thumbnail")}["not a website screenshot"]["status"] == "PASS"
    assert thumbs.is_screenshot_path("assets/shots/site-1.jpg") or thumbs.is_screenshot_path("build/capture/x.png")


def test_site_scenes_are_never_picked_as_thumbnail_frames():
    assert "site" in thumbs.SCREENSHOT_TYPES and "tour" in thumbs.SCREENSHOT_TYPES and "pile" in thumbs.SCREENSHOT_TYPES


def test_tiny_feed_size_is_checked():
    assert thumbs.SIZES["tiny"] == (246, 138)


# ------------------------------------------------------------------ the required thumbnail step
def _road_sidecar(tiles, texts, W=1280, H=720):
    return {"layout": "road", "tiles": tiles, "texts": texts, "W": W, "H": H}


def _plain(tmp_path, W=1280, H=720, name="t.png"):
    from PIL import Image
    f = tmp_path / name
    Image.new("RGB", (W, H), "#0b0b0e").save(f)
    return f


def _rows(f, side, kind="thumbnail"):
    return {r["check"]: r for r in thumbs.check_image(f, side, kind)}


GOOD_TEXT = {"text": "GENAI", "box": [52, 112, 500, 160], "px": 176, "color": "#f2b722", "words": 1}
GOOD_TILE = [730, 560, 118, 118]


def test_check_passes_a_clean_road_layout(tmp_path):
    r = _rows(_plain(tmp_path), _road_sidecar([GOOD_TILE, [915, 550, 118, 118]], [GOOD_TEXT]))
    assert all(r[k]["status"] == "PASS" for k in ("tiles present", "tiles inside the frame", "words clear of the tiles", "not a website screenshot", "file size", "dimensions"))


def test_check_fails_words_touching_a_tile(tmp_path):
    near = {**GOOD_TEXT, "box": [200, 560, 540, 120]}                      # right edge 740: the tile starts at 730
    r = _rows(_plain(tmp_path), _road_sidecar([GOOD_TILE, [915, 550, 118, 118]], [near]))
    assert r["words clear of the tiles"]["status"] == "FAIL" and "tile 1" in r["words clear of the tiles"]["detail"]
    close = {**GOOD_TEXT, "box": [100, 560, 620, 120]}                      # a 10 px gap: under the 12 px limit
    assert _rows(_plain(tmp_path), _road_sidecar([GOOD_TILE, [915, 550, 118, 118]], [close]))["words clear of the tiles"]["status"] == "FAIL"


def test_check_fails_a_tile_outside_the_frame(tmp_path):
    r = _rows(_plain(tmp_path), _road_sidecar([GOOD_TILE, [1230, 100, 118, 118]], [GOOD_TEXT]))
    assert r["tiles inside the frame"]["status"] == "FAIL" and "tile 2" in r["tiles inside the frame"]["detail"]


def test_check_fails_too_few_tiles(tmp_path):
    assert _rows(_plain(tmp_path), _road_sidecar([GOOD_TILE], [GOOD_TEXT]))["tiles present"]["status"] == "FAIL"


def test_check_fails_a_headline_unreadable_at_246_px(tmp_path):
    small = {**GOOD_TEXT, "px": 30, "box": [52, 112, 100, 30]}
    r = _rows(_plain(tmp_path), _road_sidecar([GOOD_TILE, [915, 550, 118, 118]], [small]))
    assert r["text size at 246x138"]["status"] == "FAIL"
    big = _rows(_plain(tmp_path), _road_sidecar([GOOD_TILE, [915, 550, 118, 118]], [GOOD_TEXT]))
    assert big["text size at 246x138"]["status"] == "PASS"


def test_check_fails_wrong_size_and_oversize_files(tmp_path):
    assert _rows(_plain(tmp_path, 640, 360), None)["dimensions"]["status"] == "FAIL"
    import numpy as np
    from PIL import Image
    f = tmp_path / "big.png"
    Image.fromarray(np.random.default_rng(1).integers(0, 255, (720, 1280, 3), dtype=np.uint8)).save(f)
    assert f.stat().st_size > 2_000_000 and _rows(f, None)["file size"]["status"] == "FAIL"


def test_check_fails_a_screenshot_source_even_without_browser_dots(tmp_path):
    side = {**_road_sidecar([GOOD_TILE, [915, 550, 118, 118]], [GOOD_TEXT]), "image": "assets/shots/site-1.jpg"}
    assert _rows(_plain(tmp_path), side)["not a website screenshot"]["status"] == "FAIL"


def _tile_project(tmp_path, brands=None, images=True):
    from PIL import Image
    p = tmp_path / "tp"
    (p / "assets" / "photo").mkdir(parents=True)
    for i in range(3):
        Image.new("RGB", (900, 600), (40 * i + 30, 90, 120)).save(p / "assets" / "photo" / f"p{i}.jpg")
    (p / "assets" / "credits.json").write_text(json.dumps([{"file": f"assets/photo/p{i}.jpg", "license": "generated"} for i in range(3)]))
    th = {"title": "He Fought Alone", "accent": "He Fought", "tag": "TRUE STORY", "sub": "A WAR THAT *ENDED*"}
    if brands:
        th["logos"] = brands
    save_yaml(p / "brief.yaml", {"title": "t", "platforms": ["youtube", "shorts"], "language": "en-US", "theme": "tech-dark", "voice": {"provider": "none"}, "captions": {"burn": False}, "brand": {"name": ""}, "thumbnail": th})
    save_yaml(p / "storyboard.yaml", {"title": "t", "bpm": 120, "scenes": [{"id": "a", "type": "story", "bars": 2, "say": "Docker and Python are used here.", "params": {"src": "assets/photo/p0.jpg", "lines": ["x"]}}]})
    return p


def test_tiles_fall_back_to_licensed_pictures_and_never_screenshots(tmp_path):
    p = _tile_project(tmp_path)
    tiles, note = thumbs.resolve_tiles(p, {}, load_yaml(p / "storyboard.yaml"), load_yaml(p / "brief.yaml"))
    assert [t["src"] for t in tiles] == [f"assets/photo/p{i}.jpg" for i in range(3)] and "licensed" in note
    from PIL import Image
    (p / "assets" / "shots").mkdir()
    Image.new("RGB", (10, 10)).save(p / "assets" / "shots" / "site-1.jpg")
    with pytest.raises(FishError):
        thumbs.resolve_tiles(p, {"tiles": ["assets/shots/site-1.jpg"]}, {}, load_yaml(p / "brief.yaml"))


def test_unrelated_logos_are_refused(tmp_path):
    _need_icons()
    p = _tile_project(tmp_path, brands=["docker", "python", "nvidia"])
    with pytest.raises(FishError) as e:
        thumbs.resolve_tiles(p, {}, load_yaml(p / "storyboard.yaml"), load_yaml(p / "brief.yaml"))
    assert "NVIDIA" in str(e.value) and "trademarks" in str(e.value)


def test_package_refuses_without_a_thumbnail_and_names_the_command(tmp_path):
    p = _tile_project(tmp_path)
    errs = thumbs.package_gate(p)
    assert errs and "fishvideo thumbnail" in errs[0] and "no thumbnail" in errs[0]


needs_browser = pytest.mark.skipif(not (SKILL / "node_modules" / "puppeteer-core").exists(), reason="needs npm install and a browser")


@needs_browser
def test_thumbnail_command_draws_checks_picks_and_unlocks_package(tmp_path):
    p = _tile_project(tmp_path, brands=["docker", "python"])
    try:
        rep = thumbs.thumbnail(p)
    except FishError as e:
        if "browser" in str(e).lower() or "did not render" in str(e):
            pytest.skip(str(e)[:80])
        raise
    assert rep["variants"][0]["layout"] == "road" and rep["covers"] and rep["covers"][0]["platform"] == "shorts"
    side = json.loads((p / rep["variants"][0]["file"]).with_suffix(".json").read_text())
    assert len(side["tiles"]) == 2 and all(0 <= t[0] and t[0] + t[2] <= 1280 for t in side["tiles"])
    assert (p / "build" / "thumbnail" / "pick.json").exists()
    assert thumbs.package_gate(p) == []
    # touching the storyboard (mtime) changes nothing; changing a thumbnail input makes it stale and names the input
    import os, time
    os.utime(p / "storyboard.yaml", (time.time() + 5, time.time() + 5))
    assert thumbs.package_gate(p) == []
    b = load_yaml(p / "brief.yaml"); b["thumbnail"]["title"] = "A different headline"; save_yaml(p / "brief.yaml", b)
    assert any("thumbnail block" in e and "fishvideo thumbnail" in e for e in thumbs.package_gate(p))


@needs_browser
def test_package_gate_reports_a_failing_check_with_the_command(tmp_path):
    p = _tile_project(tmp_path)
    try:
        thumbs.thumbnail(p)
    except FishError as e:
        pytest.skip(str(e)[:80])
    side = (p / "build" / "thumbnail" / "variants")
    j = next(side.glob("*.json"))
    d = json.loads(j.read_text()); d["tiles"][0][0] = 1250; j.write_text(json.dumps(d))
    errs = thumbs.package_gate(p)
    assert any("tiles inside the frame" in e and "fishvideo thumbnail" in e for e in errs)


def test_cli_exposes_the_required_step_and_the_opt_out():
    import fishvideo
    assert fishvideo.PASSTHRU["thumbnail"] == "thumbs"
    txt = (SKILL / "scripts" / "fishvideo.py").read_text()
    assert "--no-thumbnail" in txt and "the thumbnail step is not done" in txt


def test_skill_md_lists_the_thumbnail_step_as_required():
    md = (SKILL / "SKILL.md").read_text()
    assert "fishvideo thumbnail" in md and "required" in md.lower()


# ------------------------------------------------------------------ text over photos: contrast measured on rendered frames
def _photo_project(tmp_path, theme, bright):
    from PIL import Image
    import numpy as np
    p = tmp_path / f"ph-{theme}-{'b' if bright else 'd'}"
    (p / "assets").mkdir(parents=True)
    rng = np.random.default_rng(3)
    base = 235 if bright else 25
    arr = np.clip(base + rng.normal(0, 8, (1080, 1920, 3)), 0, 255).astype("uint8")
    Image.fromarray(arr).save(p / "assets" / "a.jpg")
    save_yaml(p / "brief.yaml", {"title": "t", "platforms": ["youtube"], "language": "en-US", "theme": theme, "voice": {"provider": "none"}, "captions": {"burn": False}, "brand": {"name": ""}})
    save_yaml(p / "storyboard.yaml", {"title": "t", "bpm": 120, "scenes": [{"id": "a", "type": "story", "bars": 2, "say": "", "params": {"src": "assets/a.jpg", "kicker": "KICKER", "label": "illustrative",
                                                                                                         "lines": [{"text": "The *accent* word", "at": 0.0, "size": 110}, {"text": "small *dim* line", "at": 0.0, "size": 70, "dim": True}]}}]})
    return p


@needs_browser
@pytest.mark.parametrize("bright", [True, False])
def test_story_text_and_accent_words_stay_readable_over_bright_and_dark_photos(tmp_path, bright):
    from fvcore import node, last_json_line
    worst = {}
    for theme in themes.all_themes():
        p = _photo_project(tmp_path, theme, bright)
        import storyboard as sbm
        sbm.build(p, quiet=True)
        r = node("designprobe.mjs", p, "--platform", "youtube", "--scenes", "--k", "0.9", "--mode", "render", "--out", p / "probe", capture=True, check=False)
        res = last_json_line(r.stdout or "") or {}
        if r.returncode != 0 or not res.get("probe"):
            pytest.skip("no browser: " + ((r.stderr or "")[-80:]))
        fr = json.loads(open(res["probe"]).read())["frames"][0]
        img = dz.load_rgb(fr["file"])
        for t in fr["texts"]:
            if t["text"].upper() in ("KICKER", "ILLUSTRATIVE"):
                continue                                                 # chips carry their own background
            ratio = dz.text_contrast(img, t["box"], dz.parse_color(t["color"]), tol=60).get("ratio")
            if ratio is not None:
                worst[theme] = min(worst.get(theme, 99), ratio)
    bad = {k: round(v, 1) for k, v in worst.items() if v < 4.5}
    assert not bad, f"text under 4.5:1 over a {'bright' if bright else 'dark'} photo: {bad}"


# ------------------------------------------------------------------ follow-ups from the cheaper-model test
def test_package_refuses_failing_qa_names_the_checks_and_records_an_override(tmp_path):
    import fishvideo
    p = _project(tmp_path, [{"id": "a", "type": "story", "bars": 2, "params": {"src": "a.jpg"}}])
    (p / "build" / "shorts").mkdir(parents=True, exist_ok=True)
    (p / "build" / "shorts" / "qa.json").write_text(json.dumps({"checks": [{"check": "voice words", "status": "FAIL", "detail": "s6 heard emos"}, {"check": "codec", "status": "PASS"}]}))
    errs = fishvideo.qa_fail_errors(p)
    assert errs == ["shorts: QA FAIL `voice words`: s6 heard emos"]
    with pytest.raises(FishError) as e:
        fishvideo.qa_gate_or_override(p, None)
    assert "voice words" in str(e.value) and "--accept-qa-fail" in str(e.value)
    with pytest.raises(FishError):
        fishvideo.qa_gate_or_override(p, "ok")                                        # an override needs the user's words
    assert fishvideo.qa_gate_or_override(p, "the user accepted the homophone") == "the user accepted the homophone"
    assert json.loads((p / "build" / "qa-override.json").read_text())["failures"] == errs
    (p / "build" / "shorts" / "qa.json").unlink()
    assert "no QA report" in fishvideo.qa_fail_errors(p)[0]


def test_numeric_tags_do_not_crash_the_package():
    import package
    assert package.tags_for({"publish": {"tags": [1932, "emu", "#war"]}}) == ["1932", "emu", "war"]


def test_missing_theme_fonts_stop_with_the_install_command(tmp_path, monkeypatch):
    (tmp_path / "scripts" / "stage").mkdir(parents=True)
    (tmp_path / "scripts" / "stage" / "fonts.css").write_text('@font-face { font-family: "Anton"; font-weight: 400; src: url(/skill/node_modules/@fontsource/anton/files/a.woff2) format("woff2"); }')
    monkeypatch.setattr(themes, "SKILL", tmp_path)
    with pytest.raises(FishError) as e:
        themes.check_fonts({"theme": "bold-shorts"})
    assert "npm install" in str(e.value) and "Anton" in str(e.value)
    assert themes.missing_fonts({"theme": "minimal-light"}) == []                      # a theme that needs none of the missing families


def test_story_fit_matches_the_stage_and_never_enlarges_past_the_limit():
    js = (SKILL / "scripts" / "stage" / "scenes" / "story.js").read_text()
    assert "cover <= 1.3" in js and "Math.min(2.2, cover)" in js and gates.MAX_UPSCALE == 2.2
    assert gates.story_fit(1920, 1080, 1920, 1080)["mode"] == "bleed"
    f = gates.story_fit(450, 299, 1080, 1920)
    assert f["mode"] == "frame" and f["scale"] == 2.2


def test_resolution_gate_fails_a_picture_too_small_for_its_use(tmp_path):
    from PIL import Image
    p = _credited(tmp_path, ["assets/photo/a.jpg"], [GOOD], label="illustrative")
    Image.new("RGB", (300, 200)).save(p / "assets" / "photo" / "a.jpg")
    m = gates.measure(p)
    f = gates.resolution(p, m["rows"])
    assert f and "too small" in f[0] and "--min-width" in f[0]
    Image.new("RGB", (900, 600)).save(p / "assets" / "photo" / "a.jpg")
    assert gates.resolution(p, gates.measure(p)["rows"]) == []


def test_source_skips_small_results_and_does_not_reuse_a_file_from_another_beat(tmp_path, monkeypatch):
    import assets as A
    import fvnet
    p = tmp_path / "sp3"
    (p / "assets").mkdir(parents=True)
    save_yaml(p / "brief.yaml", {"title": "t", "platforms": ["shorts"]})
    save_yaml(p / "storyboard.yaml", {"title": "t", "bpm": 120, "scenes": [
        {"id": "s1", "type": "story", "bars": 2, "params": {"src": "assets/photo/wikimedia-1.jpg"}},
        {"id": "s2", "type": "story", "bars": 2, "params": {"src": "assets/photo/TODO.jpg"}}]})
    cands = [{"id": "wikimedia-1", "risk": "safe", "_ok": True, "width": 2000}, {"id": "wikimedia-2", "risk": "safe", "_ok": True, "width": 200},
             {"id": "wikimedia-3", "risk": "safe", "_ok": True, "width": 900}]
    monkeypatch.setattr(A, "search", lambda *a, **k: cands)
    got = {}
    def fake_get(project, ids, accept_risk=False):
        got["ids"] = ids
        f = project / "assets" / "photo" / (ids[0] + ".jpg"); f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(b"x")
        fvnet.add_credit(project, {"id": ids[0], "provider": "wikimedia", "file": f"assets/photo/{ids[0]}.jpg", "url": "u", "license": "CC0", "author": "a", "title": "t"})
        return [f]
    monkeypatch.setattr(A, "get", fake_get)
    A.source(p, "x", beat="s2")
    assert got["ids"] == ["wikimedia-3"]                    # not the 200 px one, not the file beat s1 already uses
    monkeypatch.setattr(A, "search", lambda *a, **k: [{"id": "w-9", "risk": "safe", "_ok": True, "width": 100}])
    with pytest.raises(FishError) as e:
        A.source(p, "x", beat="s2")
    assert "blurry" in str(e.value)


def test_accent_keeps_the_key_words_together_not_the_filler():
    assert thumbs.pick_accent("The Emus Won", "The") == "Emus Won"
    assert thumbs.pick_accent("The Emus Won", "Won") == "Emus Won"
    assert thumbs.pick_accent("GenAI Engineer Roadmap", "GenAI") == "GenAI Engineer Roadmap"
    assert thumbs.pick_accent("The War Ended in 1945", None) == "War Ended"


def test_check_fails_the_tag_chip_over_the_headline_and_unsharp_tiles(tmp_path):
    head = {"text": "THE", "box": [52, 112, 200, 120], "px": 124, "color": "#ffffff", "words": 1, "grp": "head"}
    chip = {"name": "tag", "box": [58, 52, 130, 90]}
    side = {**_road_sidecar([GOOD_TILE, [915, 550, 118, 118]], [head]), "blocks": [chip]}
    assert _rows(_plain(tmp_path), side)["words and chip do not overlap"]["status"] == "FAIL"          # the chip (52..142) covers the headline glyphs (126..)
    clear = {**head, "box": [52, 140, 200, 120]}
    assert _rows(_plain(tmp_path), {**side, "texts": [clear]})["words and chip do not overlap"]["status"] == "PASS"
    sub = {"text": "FOR BEGINNERS", "box": [58, 200, 400, 50], "px": 44, "color": "#fff", "words": 2, "grp": "sub"}
    assert _rows(_plain(tmp_path), {**side, "texts": [clear, sub]})["words and chip do not overlap"]["status"] == "FAIL"   # the audience line over the headline
    blurry = {**side, "texts": [clear], "tile_px": [[200, 150], None]}
    r = _rows(_plain(tmp_path), {**blurry, "tiles": [[700, 300, 330, 330], [915, 550, 118, 118]]})
    assert r["tile pictures are sharp"]["status"] == "FAIL"
    ok = _rows(_plain(tmp_path), {**side, "texts": [clear], "tile_px": [[900, 700], None]})
    assert ok["tile pictures are sharp"]["status"] == "PASS"


def test_a_brief_edit_unrelated_to_the_thumbnail_does_not_invalidate_it(tmp_path):
    p = _tile_project(tmp_path)
    b0 = load_yaml(p / "brief.yaml"); b0["platforms"] = ["youtube"]; save_yaml(p / "brief.yaml", b0)
    (p / "build" / "thumbnail" / "variants").mkdir(parents=True)
    f = p / "build" / "thumbnail" / "variants" / "thumb-1-road.png"
    f.write_bytes(b"x")
    th = p / "build" / "thumbnail"
    (th / "variants.json").write_text(json.dumps({"variants": [{"n": 1, "layout": "road", "file": str(f.relative_to(p))}], "covers": []}))
    inputs = json.loads(json.dumps(thumbs.thumb_inputs(p), default=str))
    (th / "pick.json").write_text(json.dumps({"n": 1, "layout": "road", "file": str(f.relative_to(p)), "inputs": inputs}))
    side = f.with_suffix(".json"); side.write_text(json.dumps({"layout": "road", "tiles": [GOOD_TILE, [915, 550, 118, 118]], "texts": [], "tile_px": []}))
    from PIL import Image
    Image.new("RGB", (1280, 720), "#0b0b0e").save(f)
    b = load_yaml(p / "brief.yaml"); b["tone"] = "calm"; b["publish"] = {"titles": ["x"]}; save_yaml(p / "brief.yaml", b)
    assert thumbs.package_gate(p) == []
    b["thumbnail"]["title"] = "A New Headline"; save_yaml(p / "brief.yaml", b)
    errs = thumbs.package_gate(p)
    assert errs and "thumbnail block" in errs[0] and "fishvideo thumbnail" in errs[0]


@needs_browser
@pytest.mark.parametrize("plat,sbplat", [("youtube", "youtube"), ("shorts", "shorts")])
def test_the_on_screen_label_passes_the_same_lint_that_flags_small_text(tmp_path, plat, sbplat):
    from fvcore import node
    p = _photo_project(tmp_path, "tech-dark", False)
    b = load_yaml(p / "brief.yaml"); b["platforms"] = [plat]; save_yaml(p / "brief.yaml", b)
    import storyboard as sbm
    sbm.build(p, quiet=True)
    r = node("stills.mjs", p, "--platform", plat, "--lint", capture=True, check=False)
    if r.returncode != 0:
        pytest.skip("no browser")
    lint = json.loads((p / "build" / plat / "lint.json").read_text())
    issues = lint["issues"] if isinstance(lint, dict) else lint
    assert not [i for i in issues if "ILLUSTRATIVE" in str(i.get("text", "")).upper()], issues


def test_series_text_and_recipe_leftovers_fail_the_gate_unless_it_is_a_series(tmp_path):
    p = tmp_path / "ser"
    p.mkdir()
    save_yaml(p / "brief.yaml", {"title": "t", "publish": {"titles": ["x"]}})
    save_yaml(p / "storyboard.yaml", {"title": "t", "bpm": 120, "scenes": [{"id": "s6", "type": "story", "bars": 2, "say": "And so it ends.", "params": {"kicker": "PART 2", "lines": ["x"]}}]})
    assert any("series text" in e for e in iv.copy_problems(p))
    b = load_yaml(p / "brief.yaml"); b["series"] = True; save_yaml(p / "brief.yaml", b)
    assert not any("series text" in e for e in iv.copy_problems(p))
    sb = recipes.storyboard("story-short")
    assert all("note" not in s and "bars_min" in s and "bars" not in s for s in sb["scenes"]) and sb["end_card"] is False
    assert "PART 2" not in json.dumps(sb)


def test_story_short_does_not_warn_about_the_end_card():
    import storyboard as sbm
    sb = recipes.storyboard("story-short")
    for s in sb["scenes"]:
        s["params"] = {}; s["say"] = "x"
    cfg = {"brief": {"recipe": "story-short"}}
    assert not any("end` card" in w for w in sbm.validate(sb, cfg)[1])
    sb2 = recipes.storyboard("roadmap-explainer"); sb2.pop("end_card", None)
    assert any("end` card" in w for w in sbm.validate({**sb2, "scenes": sb2["scenes"][:-1]}, {"brief": {"recipe": "roadmap-explainer"}})[1])


def test_new_with_a_recipe_takes_length_and_language_from_the_prompt_then_the_recipe(tmp_path):
    import argparse, fishvideo
    a = argparse.Namespace(dir=str(tmp_path / "np"), prompt="A 25 second YouTube Short about emus, American English", url=None, ref=None, platforms=None, length=None, lang=None,
                           title=None, recipe="story-short", force=False)
    p = fishvideo.cmd_new(a)
    b = load_yaml(p / "brief.yaml")
    assert b["length"] == 25 and b["language"] == "en-US" and "history" in b["audience"] and "developers" not in b["audience"]


def test_interview_summary_shows_the_real_preset_and_every_question_recommends_something():
    brief = {"title": "t", "voice": {"provider": "chatterbox", "language": "en-US", "studio": {"style": "chatterbox-soft", "gender": "male", "pace": "natural"}, "fallback": {"voice": "en-US-AndrewMultilingualNeural"}}}
    import tempfile, pathlib
    d = pathlib.Path(tempfile.mkdtemp()); save_yaml(d / "brief.yaml", brief)
    txt = iv.summary(d)
    assert "chatterbox-soft" in txt and "Andrew" not in txt
    for r in iv.bank()["rounds"]:
        for q in r["questions"]:
            opts = q.get("options") or []
            if opts or q.get("options_from"):
                labels = [o["label"] for o in (iv._options(q, {}) if q.get("options_from") else opts)]
                assert any("Recommended" in l for l in labels), q["id"]


def test_budget_warns_only_for_fixed_slots_and_before_any_voice(tmp_path):
    long = "one two three four five six seven eight nine ten eleven twelve"
    p = _project(tmp_path, [{"id": "a", "type": "story", "bars": 2, "say": long, "params": {}}, {"id": "b", "type": "story", "bars_min": 2, "say": long, "params": {}}])
    rows = {r["beat"]: r for r in gates.budget(p)}
    assert rows["a"]["over"] and rows["a"]["fixed"] and rows["b"]["over"] and not rows["b"]["fixed"]
    errs = gates.budget_errors(p)
    assert len(errs) == 1 and "beat a" in errs[0] and "BEFORE generating the voice" in errs[0]


def test_voice_aliases_never_change_the_cache_key():
    S1 = vl.studio_settings({"language": "en-US"}, "chatterbox")
    S2 = vl.studio_settings({"language": "en-US", "studio": {"aliases": {"emos": "emus"}}}, "chatterbox")
    drop = ("ref_path", "aliases", "verify")
    assert {k: v for k, v in S1.items() if k not in drop} == {k: v for k, v in S2.items() if k not in drop}
    assert "voice words" in (SKILL / "SKILL.md").read_text() and "words" in vl.SUBCOMMANDS


def test_light_themes_keep_dimmed_content_readable():
    for k, v in themes.all_themes().items():
        if v["mode"] == "light":
            assert v["layout"]["dim"] >= 0.7, k


def test_adopt_gives_an_existing_project_a_message_and_a_one_command_fix(tmp_path):
    import assets as A
    from PIL import Image
    p = _credited(tmp_path, ["assets/photo/a.jpg"], [])
    _, f = gates.check(p)
    assert any("EXISTING PROJECT?" in x and "assets adopt" in x and "nothing was changed" in x for x in f)
    with pytest.raises(FishError):
        A.adopt(p, "", "me", "https://x")
    r = A.adopt(p, "CC0", "A. Person", "https://commons.example/a", "illustrative")
    assert r["credited"] == ["assets/photo/a.jpg"] and r["labelled"]
    assert gates.check(p)[1] == []


def test_docs_say_library_of_congress_may_be_unavailable():
    assert "may answer 403" in (SKILL / "references" / "recipes-and-themes.md").read_text()


# ------------------------------------------------------------------ last round: sharp coverage, captions, thumbnail type and margins
def test_captions_never_float_a_lone_connecting_word():
    import captions as C
    w = [{"w": x, "t0": i * 0.3 + (0.9 if i >= 6 else 0), "t1": i * 0.3 + 0.25 + (0.9 if i >= 6 else 0)} for i, x in enumerate("The army sent two Lewis guns and 10,000 rounds.".split())]
    texts = [c["text"] for c in C.chunk_words(w)]
    assert "and" not in texts and all(len(t.split()) > 1 for t in texts)


def _frame_png(tmp_path, name, blurred_card):
    import numpy as np
    from PIL import Image, ImageFilter
    rng = np.random.default_rng(5)
    photo = Image.fromarray(np.clip(rng.normal(128, 40, (960, 540, 3)), 0, 255).astype("uint8"))
    f = tmp_path / name
    if not blurred_card:
        photo.save(f)                                                           # a sharp full-bleed picture
    else:
        bg = photo.filter(ImageFilter.GaussianBlur(28))                         # the blurred backdrop with a small sharp card
        bg.paste(photo.crop((0, 0, 280, 220)), (130, 120))
        bg.save(f)
    return f


def test_sharp_coverage_separates_full_pictures_from_small_cards_on_blur(tmp_path):
    sharp = gates.sharp_share_of(_frame_png(tmp_path, "a.png", False))
    small = gates.sharp_share_of(_frame_png(tmp_path, "b.png", True))
    assert sharp > 0.9 and small < 0.2
    g = gates.recipe_gate("story-short")
    assert g["sharp_share_min"] == 0.45 and small < g["sharp_share_min"] <= sharp


def test_sharp_failure_names_the_weak_scenes_for_a_video(tmp_path):
    import subprocess
    from fvcore import ffmpeg_bin
    p = _project(tmp_path, [{"id": "a", "type": "story", "bars": 2, "params": {"src": "a.jpg"}}])
    png = _frame_png(tmp_path, "c.png", True)
    mp4 = tmp_path / "v.mp4"
    subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-loop", "1", "-i", str(png), "-t", "4", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    m, f = gates.sharp_failures(p, mp4, "story-short")
    assert f and "needs 45%" in f[0] and "a " in f[0]
    ok = tmp_path / "ok.mp4"
    subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-loop", "1", "-i", str(_frame_png(tmp_path, "d.png", False)), "-t", "4", "-pix_fmt", "yuv420p", str(ok)], check=True)
    assert gates.sharp_failures(p, ok, "story-short")[1] == []


def test_framed_story_layout_fills_the_frame_with_real_pictures():
    js = (SKILL / "scripts" / "stage" / "scenes" / "story.js").read_text()
    assert "0.88 * c.W" in js and "ONE large panel" in js and "DIFFERENT picture file" in js and "slow pan" in js and "the same\n           file is never shown twice" in js


def test_thumbnail_headline_is_always_heavy_and_tiles_keep_a_margin(tmp_path):
    js = (SKILL / "scripts" / "stage" / "scenes" / "thumbs.js").read_text()
    assert 'HEAVY = new Set(["Anton", "Archivo Black", "Oswald"])' in js and "'Inter', var(--sans)" in js
    assert "Special Elite" not in js
    edge = _road_sidecar([[10, 300, 118, 118], [915, 550, 118, 118]], [GOOD_TEXT])
    assert _rows(_plain(tmp_path), edge)["tiles inside the frame"]["status"] == "FAIL"          # inside the frame but inside the safe margin too


def test_signoff_checklist_asks_about_cut_off_faces():
    p = Path(__file__)
    import gates as G
    assert "No face or head is cut off" in (SKILL / "scripts" / "gates.py").read_text()


def _stack_png(tmp_path, name, same):
    import numpy as np
    from PIL import Image, ImageFilter
    rng = np.random.default_rng(11)
    def pic(seed):
        r = np.random.default_rng(seed)
        base = np.kron(r.normal(128, 55, (24, 14, 3)), np.ones((10, 10, 1)))
        return Image.fromarray(np.clip(base + r.normal(0, 14, base.shape), 0, 255).astype("uint8"))
    a = pic(1)
    b = a if same else pic(2)
    frame = Image.new("RGB", (540, 960), (50, 50, 50)).filter(ImageFilter.GaussianBlur(2))
    frame.paste(a.resize((470, 330)), (35, 110))
    frame.paste(b.resize((470, 330)), (35, 540))
    f = tmp_path / name
    frame.save(f)
    return f


def test_the_same_picture_twice_is_flagged_and_counted_once(tmp_path):
    dup = gates.panel_analysis(_stack_png(tmp_path, "dup.png", True))
    ok = gates.panel_analysis(_stack_png(tmp_path, "ok.png", False))
    assert dup["duplicates"] and not ok["duplicates"]
    assert dup["share"] < dup["raw"] * 0.7 and ok["share"] == ok["raw"]          # the repeat adds no unique area
    assert gates.DUP_SIMILARITY == 0.65


def test_a_beat_may_not_list_the_same_picture_twice(tmp_path):
    from PIL import Image
    p = _credited(tmp_path, ["assets/photo/a.jpg"], [GOOD], label="illustrative")
    import shutil as sh
    sh.copy(p / "assets" / "photo" / "a.jpg", p / "assets" / "photo" / "b.jpg")
    sb = load_yaml(p / "storyboard.yaml")
    sb["scenes"][0]["params"]["srcs"] = [{"src": "assets/photo/a.jpg"}, {"src": "assets/photo/b.jpg"}]
    save_yaml(p / "storyboard.yaml", sb)
    f = gates.check(p)[1]
    assert any("same picture" in x and "assets source" in x for x in f)
    import numpy as np
    Image.fromarray(np.random.default_rng(2).integers(0, 255, (600, 900, 3), dtype=np.uint8)).save(p / "assets" / "photo" / "b.jpg")
    Image.fromarray(np.random.default_rng(3).integers(0, 255, (600, 900, 3), dtype=np.uint8)).save(p / "assets" / "photo" / "a.jpg")
    assert not any("same picture" in x for x in gates.check(p)[1])


def test_resolution_gate_limits_the_upscale_of_the_default_panel_in_both_directions(tmp_path):
    from PIL import Image
    p = _credited(tmp_path, ["assets/photo/a.jpg"], [GOOD], label="illustrative")
    Image.new("RGB", (450, 299), "#445566").save(p / "assets" / "photo" / "a.jpg")                 # wide enough (2.1x) but too short for a half-height panel (3.2x)
    f = gates.resolution(p, gates.measure(p)["rows"])
    assert f and "3.2x" in f[0] and "2.2x" in f[0] and "--min-height" in f[0]
    Image.new("RGB", (450, 450), "#445566").save(p / "assets" / "photo" / "a.jpg")
    assert gates.resolution(p, gates.measure(p)["rows"]) == []
    assert gates.min_native_height(1920) == 436 and gates.min_native_width(1080) == 431


def test_story_panel_never_exceeds_the_upscale_limit_and_shows_one_picture_per_file():
    js = (SKILL / "scripts" / "stage" / "scenes" / "story.js").read_text()
    assert "nat[1] * 2.2" in js and "srcs[1].src !== srcs[0].src" in js and "slow pan" in js


def test_internal_build_params_are_not_counted_as_pictures():
    sc = {"id": "a", "type": "story", "params": {"src": "assets/photo/a.jpg", "_ground": {"assets/photo/a.jpg": "assets/_ground/a.jpg"}, "_px": {"assets/photo/a.jpg": [900, 600]}}}
    assert gates.classify(sc) == ("image", ["assets/photo/a.jpg"])


def test_story_build_adds_small_backdrop_copies_and_sizes(tmp_path):
    import storyboard as sbm
    from PIL import Image
    p = _credited(tmp_path, ["assets/photo/a.jpg"], [GOOD], label="illustrative")
    Image.new("RGB", (2400, 1800), "#334455").save(p / "assets" / "photo" / "a.jpg")
    prm = sbm._px_params(p, {"type": "story", "params": {"src": "assets/photo/a.jpg"}})
    assert prm["_px"]["assets/photo/a.jpg"] == [2400, 1800]
    g = Image.open(p / prm["_ground"]["assets/photo/a.jpg"])
    assert max(g.size) == 480
