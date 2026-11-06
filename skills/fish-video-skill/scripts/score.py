"""Per-project synthesised score: key, mode, progression, tempo and instrument palette drawn from a mood, seeded by the brief
and the trend direction, and stored in <project>/score.json so a render is repeatable (delete the file to re-draw).

    python scripts/score.py <project>          print the score this project gets
    python scripts/score.py compare <a> <b>    show how two projects differ

`score: {fixed: true, ...}` in the brief or storyboard keeps exactly the values written there."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fvcore import SKILL, load_json, load_yaml, log, main_guard, save_json


def _cfg() -> dict:
    return load_yaml(SKILL / "config" / "scores.yaml")


def _direction_text(project: Path) -> str:
    try:
        import trends
        d = trends.direction_of(project)
        return json.dumps(d, sort_keys=True, default=str) if d else ""
    except Exception:
        return ""


def basis(project: Path, brief: dict) -> str:
    """The text the seed comes from: what the video is about plus the live trend direction."""
    keys = ("title", "summary", "prompt", "topic", "audience", "goal")
    about = {k: brief.get(k) for k in keys if brief.get(k)}
    return json.dumps({"about": about, "name": Path(project).name, "direction": _direction_text(Path(project))}, sort_keys=True, default=str)


def _h(text: str, salt: str) -> int:
    return int(hashlib.sha1((salt + "|" + text).encode()).hexdigest()[:12], 16)


def pick_mood(cfg: dict, brief: dict, text: str) -> str:
    moods = cfg["moods"]
    named = (brief.get("music") or {}).get("mood")
    if named in moods:
        return named
    low = text.lower()
    scored = sorted(((sum(low.count(w) for w in ws), m) for m, ws in cfg["keywords"].items()), reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][1]
    names = sorted(moods)
    return names[_h(text, "mood") % len(names)]


def derive(project, brief: dict, explicit: dict | None = None, reseed: bool = False) -> dict:
    """The score for this project. Reads score.json when it exists; otherwise draws it and writes the file."""
    project = Path(project)
    explicit = explicit or {}
    if explicit.get("fixed"):
        return {k: v for k, v in explicit.items() if k != "fixed"}
    f = project / "score.json"
    if f.exists() and not reseed:
        try:
            return load_json(f)
        except Exception:
            pass
    cfg = _cfg()
    text = basis(project, brief)
    mood = pick_mood(cfg, brief, text)
    m = cfg["moods"][mood]
    pick = lambda salt, seq: seq[_h(text, salt) % len(seq)]
    lo, hi = m["bpm"]
    leads = list(m["leads"])
    r = _h(text, "leads") % len(leads)
    score = {
        "mood": mood, "seed": _h(text, "seed") % 2147483647 or 1, "key": pick("key", m["keys"]), "mode": pick("mode", m["modes"]),
        "progression": pick("prog", m["progressions"]), "bpm": lo + _h(text, "bpm") % (hi - lo + 1), "drums": bool(m["drums"]),
        "palette": {"leads": leads[r:] + leads[:r], "arp": _h(text, "arp") % 4, "bass": _h(text, "bass") % 4, "drum": m.get("drum", "four")},
        "basis": hashlib.sha1(text.encode()).hexdigest()[:10],
    }
    for k in ("sfx", "drums"):                      # an explicit switch in the brief still wins
        if k in explicit:
            score[k] = explicit[k]
    save_json(f, score)
    return score


def signature(score: dict) -> tuple:
    return (score.get("seed"), score.get("key"), score.get("mode"), score.get("progression"), score.get("bpm"), json.dumps(score.get("palette"), sort_keys=True))


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="score.py")
    ap.add_argument("project", nargs="+")
    ap.add_argument("--reseed", action="store_true")
    a = ap.parse_args(argv)
    ps = a.project[1:] if a.project[0] == "compare" else a.project
    out = []
    for p in ps:
        b = load_yaml(Path(p) / "brief.yaml") if (Path(p) / "brief.yaml").exists() else {}
        out.append(derive(p, b, reseed=a.reseed))
        log(f"{p}: {json.dumps(out[-1])}")
    if a.project[0] == "compare" and len(out) == 2:
        log("different" if signature(out[0]) != signature(out[1]) else "SAME score")
    return 0


if __name__ == "__main__":
    main_guard(cli)
