"""Recipes: proven video formats as a starting point.

    fishvideo recipes                         list them
    fishvideo new <dir> --recipe <id> --prompt "..."     a project with the recipe's brief, storyboard skeleton and asset plan

The storyboard is a skeleton: scene types, order, timing and notes. Every word is a TODO, so `fishvideo gate`
refuses to render until you write it. The recipe's `gate:` thresholds are enforced by `fishvideo gates`.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from fvcore import SKILL, FishError, load_yaml, log, main_guard, save_yaml

_CFG = None
TODO_PARAMS = {
    "story": {"src": "assets/photo/TODO.jpg", "kicker": "TODO", "lines": [{"text": "TODO", "word": "TODO"}]},
    "pile": {"cards": [{"src": "assets/shots/TODO.jpg", "url": "TODO", "x": 0.5, "y": 0.5, "w": 0.5}], "title": "TODO", "title_word": "TODO"},
    "statement": {"src": "assets/photo/TODO.jpg", "lines": ["TODO", "TODO"]},
    "roadmap": {"nodes": [{"tag": "TODO", "label": "TODO", "glyph": "TODO"}], "visits": [{"i": 0, "t": 0}], "open_wide": 1.0},
    "site": {"src": "assets/shots/TODO.jpg", "url": "TODO", "title": "TODO", "notes": ["TODO"]},
    "cards": {"title": "TODO", "items": [{"tag": "TODO", "t": "TODO", "d": "TODO"}]},
    "footage": {"clip": "TODO", "title": "TODO"},
    "end": {"name": "TODO", "tagline": "TODO"},
    "bold": {"shape": "burst", "g": "TODO", "lines": [{"text": "TODO", "word": "TODO"}]},
    "kstack": {"lines": ["TODO", "**TODO**"], "element": "none"},
}


def config() -> dict:
    global _CFG
    if _CFG is None:
        _CFG = load_yaml(SKILL / "config" / "recipes.yaml")
    return _CFG


def all_recipes() -> dict:
    return config()["recipes"]


def get(name: str) -> dict:
    r = all_recipes().get(name)
    if r is None:
        raise FishError(f"unknown recipe '{name}': one of {', '.join(all_recipes())} (fishvideo recipes)")
    return r


def points_for_length(recipe: dict, length: float | None = None) -> int:
    """How many repeated points a recipe has at this length (s): recipes with a `points:` rule scale with it, the rest keep `steps`."""
    rule = recipe.get("points")
    if not rule or not length:
        return int(recipe.get("steps", 3))
    n = round((float(length) - float(rule.get("base_s", 12))) / float(rule.get("per_point_s", 12)))
    return max(int(rule.get("min", 2)), min(int(rule.get("max", 5)), n))


def expand(recipe: dict, length: float | None = None, optional: bool = False) -> list[dict]:
    """The beat list with `repeat: step` blocks unrolled. `optional` beats (an interview decision, e.g. a CTA) are left out unless asked for."""
    out = []
    for b in recipe["beats"]:
        if "repeat" in b:
            for n in range(1, points_for_length(recipe, length) + 1):
                for s in b["scenes"]:
                    out.append({**s, "id": s["id"].format(n=n)})
        elif b.get("optional") and not optional:
            continue
        else:
            out.append(b)
    return out


def storyboard(name: str, length: float | None = None) -> dict:
    r = get(name)
    scenes = []
    for b in expand(r, length):
        sc = {"id": b["id"], "type": b["type"], "bars_min": b["bars"], "transition": "cut" if b["type"] != "footage" else "flash",
              "say": "TODO: narration for this beat", "params": _clone(TODO_PARAMS.get(b["type"], {}))}
        scenes.append(sc)
    return {"title": "TODO", "bpm": 120, "style": r.get("style"), "texture": None, "scenes": scenes, **({"end_card": False} if r.get("end_card") is False else {}), **({"background": r["background"]} if r.get("background") else {}), **({"vignette": False} if r.get("vignette") is False else {}),
            "thumbnail": {"title": "TODO", "logos": []}}


def _clone(o):
    import copy
    return copy.deepcopy(o)


def brief_over(name: str) -> dict:
    r, sh = get(name), config()["shared"]
    pacing = {**sh["pacing"], **(r.get("pacing") or {})}
    return {"recipe": name, "audience": r.get("audience"), "language": r.get("language"), "theme": r["theme"], "structure": r["structure"], "goal": r["goal"], "platforms": r["platforms"], "length": r["length"],
            "style": r.get("style"), "pacing": pacing, "mix": {**sh["mix"], **(r.get("mix") or {})}, "voice": sh["voice"], "captions": {**sh["captions"], **(r.get("captions") or {})},
            "music": {"mood": r.get("music")}, **({"sfx": r["sfx"]} if r.get("sfx") else {})}


def asset_plan(name: str, length: float | None = None) -> str:
    r = get(name)
    n = points_for_length(r, length)
    lines = [f"# Asset plan: {r['label']}", "", f"Recipe `{name}` (from {r['from']}). Recommended themes: {', '.join(r['themes'])}.", "",
             "Collect these BEFORE writing the storyboard. The imagery gate (`fishvideo gates <dir>`) fails the render when too little of the video shows real images.", "",
             "| need | how | count |", "|---|---|---|"]
    for a in r["assets"]:
        c = a["count"]
        lines.append(f"| {a['need']} | `{a['how']}` | {n if c == 'steps' else c} |")
    g = r["gate"]
    sec = int(60 / 120 * 4)
    lines += ["", "## Beats (the storyboard holds none of this text, so none of it can leak into the video)", "",
              f"Each beat has a minimum of `bars` x {sec} s at 120 BPM (`bars_min`); the narration then sets the real length, so a longer line stretches its beat instead of overflowing it. The word budget below is the length the beat was designed for: `fishvideo budget <dir>` shows it before any voice is generated.", "",
              "| beat | scene | bars | seconds | max words | what it is for |", "|---|---|---|---|---|---|"]
    for b in expand(r, length, optional=True):
        secs = b["bars"] * sec
        lines.append(f"| {b['id']}{' (optional)' if b.get('optional') else ''} | {b['type']} | {b['bars']} | {secs} | {max(3, int((secs - 0.6) * 2.3))} | {b['note']} |")
    lines += ["", f"Gate for this recipe: {', '.join(f'{k} {v}' for k, v in g.items())}.", ""]
    return "\n".join(lines)


def _brief_length(project: Path) -> float | None:
    """The length the brief asks for (s), so a repeatable beat block scales with it; None keeps the recipe default."""
    try:
        from fvcore import project_config
        v = project_config(project)["brief"].get("length")
        return float(v) if v else None
    except Exception:                                   # noqa: BLE001 - a missing brief just means the recipe default
        return None


def create(project: Path, name: str) -> None:
    """Add the recipe's storyboard skeleton and asset plan to a project made by `new`."""
    project = Path(project)
    get(name)
    sbf = project / "storyboard.yaml"
    if sbf.exists():
        raise FishError(f"{sbf} exists: refusing to overwrite it with a recipe skeleton")
    length = _brief_length(project)
    save_yaml(sbf, storyboard(name, length))
    (project / "assets").mkdir(exist_ok=True)
    (project / "assets" / "PLAN.md").write_text(asset_plan(name, length), encoding="utf-8")
    log(f"recipe {name}: storyboard skeleton ({len(storyboard(name, length)['scenes'])} scenes, every word a TODO) and assets/PLAN.md written")


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fishvideo recipes", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?")
    a = ap.parse_args(argv)
    if a.name:
        r = get(a.name)
        log(f"{a.name}: {r['label']}\n  from {r['from']}\n  best for: {r['best_for']}\n  themes: {', '.join(r['themes'])}\n  gate: {r['gate']}")
        return 0
    for k, r in all_recipes().items():
        log(f"  {k:<18} {r['label']:<30} {r['platforms'][0]:<8} ~{r['length']} s  themes: {', '.join(r['themes'][:3])}  | {r['best_for'][:60]}")
    return 0


if __name__ == "__main__":
    main_guard(cli)
