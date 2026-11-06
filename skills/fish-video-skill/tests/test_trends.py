"""Live trend research: enforced by the gate, searched with mocks (no network). Nothing here is a real trend."""
import datetime as dt
import json
from pathlib import Path

import pytest

import interview as iv
import recipes
import trends
import youtube
from fvcore import SKILL, load_yaml, save_json, save_yaml

NOW = dt.datetime.now(dt.timezone.utc)
GOOD_MD = """# Trend research: topic

| # | title |
|---|---|
| 1 | a |

""" + trends.ANALYSIS_HEAD + """

- Hook pattern: results #1 and #3 open on a question, #2 on a number; most are under 25 s.
- Pacing: #1-#4 cut about every second with short lines of 4 to 6 words.
- Thumbnail pattern: #1, #2 and #5 use one big word on a flat colour.
- Colour pattern: warm yellow and black dominate #1-#4; #5 is the outlier.
- Closest built-in theme and why (fallback only): bold-shorts, same flat colour and heavy type.
- What this video takes: a question hook and short lines, never a script, image or look.

```yaml
direction:
  hook: open on a question like #1 and #3
  pacing: a cut every 1.2 s with 5-word lines, as in #1-#4
  layout: photo first, one stat card in the middle (not the recipe order)
  thumbnail: one large word on flat colour as #1, #2 and #5; tiles are this video's own
  palette: derived from this run's thumbnails
```
"""


def _res(i):
    return {"id": f"id{i}", "title": f"Title {i}", "channel": "c", "views": 1000 * i, "views_per_day": 100.0 * i, "duration": 30, "is_short": True, "url": f"https://youtu.be/id{i}"}


def _proj(tmp_path, n=6, age_days=1, md=GOOD_MD, name="proj"):
    p = tmp_path / name
    (p / "research").mkdir(parents=True)
    gen = (NOW - dt.timedelta(days=age_days)).isoformat(timespec="seconds")
    save_json(p / "research" / "trends.json", {"generated": gen, "results": [_res(i) for i in range(1, n + 1)], "unavailable": None})
    (p / "research" / "trends.md").write_text(md, encoding="utf-8")
    return p


def test_fresh_research_with_analysis_passes(tmp_path):
    assert trends.gate_problems(_proj(tmp_path)) == []


def test_missing_research_fails_and_names_the_command(tmp_path):
    p = tmp_path / "x"
    p.mkdir()
    pr = trends.gate_problems(p)
    assert len(pr) == 1 and "fishvideo trends x" in pr[0] and "--unavailable" in pr[0]


def test_stale_research_fails(tmp_path):
    pr = trends.gate_problems(_proj(tmp_path, age_days=15))
    assert any("15 days old" in x for x in pr)
    assert trends.gate_problems(_proj(tmp_path, age_days=13, name="ok")) == []


def test_thin_research_fails(tmp_path):
    pr = trends.gate_problems(_proj(tmp_path, n=4))
    assert any("4 real result" in x for x in pr)
    assert trends.gate_problems(_proj(tmp_path, n=5, name="five")) == []


def test_empty_analysis_or_direction_fails(tmp_path):
    todo = GOOD_MD.replace("results #1 and #3 open on a question, #2 on a number; most are under 25 s.", "TODO")
    assert any("analysis not written" in x for x in trends.gate_problems(_proj(tmp_path, md=todo)))
    nodir = GOOD_MD.split("```yaml")[0]
    pr = trends.gate_problems(_proj(tmp_path, md=nodir, name="nd"))
    assert any("direction incomplete" in x for x in pr)
    none = GOOD_MD.split(trends.ANALYSIS_HEAD)[0]
    assert trends.gate_problems(_proj(tmp_path, md=none, name="no"))


def test_unavailable_is_recorded_and_passes_but_needs_a_real_reason(tmp_path):
    p = tmp_path / "u"
    (p / "research").mkdir(parents=True)
    (p / "brief.yaml").write_text("title: t\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        trends.mark_unavailable(p, "no")
    trends.mark_unavailable(p, "no network: DNS fails")
    assert trends.gate_problems(p) == [] and trends.unavailable_reason(p) == "no network: DNS fails"


def test_gate_includes_the_trend_check(tmp_path):
    import brief
    p = brief.new_project(tmp_path / "g", "x")
    errs = iv.gate(p, "script")
    assert any("trend research missing" in e for e in errs)


def test_recent_separates_shorts_from_long_and_widens_when_thin(tmp_path, monkeypatch):
    calls = []

    def fake_search(q, n=20, recent_days=None, shorts=False):
        calls.append((q, recent_days, shorts))
        base = [{"id": "L1", "title": "long one", "channel": "c", "views": 500, "upload_date": "20260101", "duration": 600, "views_per_day": 5.0, "is_short": False, "url": "https://youtu.be/L1"}]
        return base + ([{"id": f"S{i}", "title": f"short {i}", "channel": "c", "views": 100 * i, "upload_date": "20260101", "duration": 20, "views_per_day": 10.0 * i, "is_short": True, "url": f"https://youtu.be/S{i}"} for i in range(1, 4)] if recent_days == 90 else [])
    monkeypatch.setattr(youtube, "search", fake_search)
    monkeypatch.setattr(youtube, "search_hashtag_shorts", lambda *a, **k: [])
    monkeypatch.setattr(trends, "contact_sheet", lambda rows, out, k=12: None)
    p = tmp_path / "r"
    (p / "research").mkdir(parents=True)
    (p / "brief.yaml").write_text("title: Some topic here\nplatforms: [shorts]\n", encoding="utf-8")
    d = trends.recent(p)
    assert d["format"] == "shorts" and d["days_used"] == 90 and [c[1] for c in calls[:2]] == [30, 30]
    assert [r["id"] for r in d["results"]] == ["S3", "S2", "S1"]          # ranked by views per day, Shorts only
    assert d["counts"] == {"shorts": 3, "long": 1} and d["thin"] is True
    assert all(c[2] for c in calls)
    assert trends.ANALYSIS_HEAD in (p / "research" / "trends.md").read_text(encoding="utf-8")
    assert trends.gate_problems(p)                                          # thin + TODO analysis: still blocked
    d2 = trends.recent(p)                                                   # a re-run keeps the agent's analysis
    (p / "research" / "trends.md").write_text(GOOD_MD, encoding="utf-8")
    trends.recent(p)
    assert "results #1 and #3 open on a question" in (p / "research" / "trends.md").read_text(encoding="utf-8")


def test_format_follows_platforms():
    assert trends.format_of({"platforms": ["shorts"]}) == "shorts"
    assert trends.format_of({"platforms": ["youtube"]}) == "long"
    assert trends.format_of({"platforms": ["youtube", "shorts"]}) == "long"


# ------------------------------------------------------------------ derived theme
def _img(path, colors):
    from PIL import Image
    im = Image.new("RGB", (48, 27), colors[0])
    for i, c in enumerate(colors[1:], 1):
        im.paste(c, (i * 10, 0, i * 10 + 12, 27))
    im.save(path)
    return path


def test_derived_palette_is_pooled_contrast_checked_and_not_one_sources_look(tmp_path):
    shared = (230, 190, 20)
    files = [_img(tmp_path / f"{i}.png", [bg, shared, (240, 240, 240)]) for i, bg in enumerate([(12, 14, 30), (20, 10, 10), (10, 25, 20), (18, 18, 18)])]
    pal = trends.derive_palette(trends.thumb_palettes(files))
    assert pal["mode"] == "dark" and pal["contrast"]["ink_on_bg"] >= 4.5 and pal["contrast"]["accent_on_bg"] >= 3.0
    assert pal["min_distance_to_any_source_lead"] is not None
    with pytest.raises(SystemExit):
        trends.derive_palette(trends.thumb_palettes(files[:2]))


def test_derive_theme_writes_project_theme_and_interview_offers_it_first(tmp_path):
    import brief
    p = brief.new_project(tmp_path / "d", "x")
    r = p / "research"
    r.mkdir(exist_ok=True)
    (r / "trend-thumbs").mkdir()
    rows = []
    for i, bg in enumerate([(12, 14, 30), (20, 10, 10), (10, 25, 20), (18, 18, 18)]):
        f = _img(r / "trend-thumbs" / f"{i}.png", [bg, (230, 190, 20), (240, 240, 240)])
        rows.append({**_res(i + 1), "thumb_file": f"trend-thumbs/{f.name}"})
    save_json(r / "trends.json", {"generated": NOW.isoformat(), "results": rows})
    t = trends.derive_theme(p)
    assert t["id"] == "derived" and (r / "theme.json").exists()
    q = next(q for rr in iv.bank()["rounds"] for q in rr["questions"] if q["id"] == "theme")
    opts = iv._options(q, {}, p)
    assert opts[0]["value"] == "derived" and "Recommended" in opts[0]["label"] and not any("(Recommended)" in o["label"] for o in opts[1:])
    assert not any(o["value"] == "derived" for o in iv._options(q, {}, None))
    b = {"interview": {"answers": {"theme": "derived"}}}
    iv.apply(b, p)
    assert b["theme"] == t["base"] and b["theme_overrides"]["colors"] == t["colors"]


# ------------------------------------------------------------------ sameness and example reuse
def _sb(tmp_path, types, recipe="story-short", name="s"):
    p = tmp_path / name
    p.mkdir()
    save_yaml(p / "brief.yaml", {"title": "t", "recipe": recipe})
    save_yaml(p / "storyboard.yaml", {"title": "t", "scenes": [{"id": f"s{i}", "type": t, "say": "x"} for i, t in enumerate(types)]})
    return p


def test_sequence_identical_to_the_recipe_skeleton_fails(tmp_path):
    skel = [sc["type"] for sc in recipes.storyboard("story-short")["scenes"]]
    assert any("recipe skeleton" in e for e in iv.sameness_problems(_sb(tmp_path, skel)))
    changed = list(skel)
    changed[1] = "image" if changed[1] != "image" else "story"
    assert iv.sameness_problems(_sb(tmp_path, changed, name="c")) == []


def test_sequence_identical_to_an_example_fails_but_shared_scenes_do_not(tmp_path):
    ex = next(SKILL.glob("examples/**/storyboard.yaml"))
    seq = [sc["type"] for sc in load_yaml(ex)["scenes"]]
    assert any("examples/" in e for e in iv.sameness_problems(_sb(tmp_path, seq, recipe="bold-short")))
    assert iv.sameness_problems(_sb(tmp_path, seq[:4], recipe="bold-short", name="p")) == []     # a few shared scenes are fine


def test_an_example_image_inside_a_project_fails(tmp_path):
    media = next(p for p in (SKILL / "examples").rglob("*.jpg"))
    p = _sb(tmp_path, ["story", "image", "story"], name="e")
    (p / "assets").mkdir()
    (p / "assets" / "x.jpg").write_bytes(media.read_bytes())
    assert any("example file reused" in e for e in iv.example_problems(p))
    (p / "assets" / "x.jpg").write_bytes(b"different")
    assert iv.example_problems(p) == []


def test_example_folders_exist_and_are_documented_as_past_outputs():
    ex = SKILL / "examples"
    idx = (ex / "README.md").read_text(encoding="utf-8")
    assert "not templates" in idx and "quality bar" in idx
    for d in ("genai-roadmap-long", "onoda-story-series", "gta6-short"):
        assert (ex / d / "README.md").is_file()
