"""The up-front interview, the brief gate, approvals and voice auditions.

    fishvideo interview <dir>                    open questions, as JSON grouped by round (ask them with AskUserQuestion)
    fishvideo interview <dir> --set id=value ... record answers (value may be JSON: '["shorts","youtube"]')
    fishvideo interview <dir> --answers a.json   record many answers {id: value}
    fishvideo interview <dir> --summary          the brief as the user will hear it read back
    fishvideo interview <dir> --confirm          the user said "yes, go": freezes the interview
    fishvideo gate <dir> [--stage script|render] fail while required answers, confirmation or copy are missing
    fishvideo approve <dir> storyboard|stills|final
    fishvideo voices <dir> --audition            render the audition line in every shortlisted voice

The interview is asked ONCE, before creation. Every answer is mapped into brief.yaml
(palette -> brand.colors, music mood -> score, voice pick + delivery -> voice config,
style -> defaults), so the rest of the pipeline never needs to ask again.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from fvcore import SKILL, FishError, ensure_project, load_json, load_yaml, log, main_guard, save_json, save_yaml, secret, warn

CFG = SKILL / "config"
SERIES = re.compile(r"\bpart\s*(?:1|2|one|two)\b(?:\s*of\s*\d)?|\bto be continued\b", re.I)
PLACEHOLDER = re.compile(r"TODO|<[^<>\n]{2,80}>|lorem ipsum", re.I)
# phrases the v1 scaffold produced; they must never ship
STOCK_PHRASES = ["explained.", "in 60 seconds", "Here is ", "in three parts", "Step by step:", "Thanks for watching", "This is "]


def bank() -> dict:
    return load_yaml(CFG / "interview.yaml")


def styles() -> dict:
    return load_yaml(CFG / "styles.yaml")


def voices_cfg() -> dict:
    return load_yaml(CFG / "voices.yaml")


def _get(d: dict, path: str):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _set(d: dict, path: str, value) -> None:
    keys = path.split(".")
    cur = d
    for k in keys[:-1]:
        if not isinstance(cur.get(k), dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value


def _options(q: dict, answers: dict, project: Path | None = None) -> list[dict]:
    src = q.get("options_from")
    if not src:
        return q.get("options") or []
    st = styles()
    if src == "styles":
        return [{"label": v["label"][:40], "value": k, "description": f"{v['look']}. Best for {v['best_for']}"} for k, v in st["styles"].items()]
    if src == "themes":
        import themes
        ths = themes.all_themes()
        rec = next((k for k, v in ths.items() if v.get("style") == answers.get("style")), None) or "tech-dark"
        out = [{**o, "label": o["label"] + (" (Recommended)" if o["value"] == rec else "")} for o in themes.options()]
        out.sort(key=lambda o: "(Recommended)" not in o["label"])
        import trends
        dv = trends.derived_theme(project) if project else None
        if dv:                                    # derived from this run's live thumbnails: offered first; the built-in ones are fallbacks
            for o in out:
                o["label"] = o["label"].replace(" (Recommended)", " (fallback)")
            c = dv["colors"]
            out.insert(0, {"label": "Trend-derived (Recommended)", "value": "derived",
                           "description": f"Palette pooled from this run's trending thumbnails ({dv['mode']}; bg {c['bg']} accent {c['accent']} accent2 {c['accent2']}); type and texture from {dv['base']}"})
        out.append({"label": "No theme", "value": "none", "description": "Keep the chosen style's own palette, fonts and texture (the classic look)"})
        return out
    if src == "palettes":
        rec = (st["styles"].get(answers.get("style")) or {}).get("defaults", {}).get("palette")
        out = []
        for k, v in st["palettes"].items():
            c = v.get("colors") or {}
            desc = "Give your hex codes (bg, ink, accent)" if k == "brand" else f"bg {c.get('bg')} ink {c.get('ink')} accent {c.get('accent')}"
            out.append({"label": v["label"] + (" (Recommended)" if k == rec else ""), "value": k, "description": desc})
        if out and not any("(Recommended)" in o["label"] for o in out):
            out[0]["label"] += " (Recommended)"
        out.sort(key=lambda o: "(Recommended)" not in o["label"])
        return out
    if src == "music_moods":
        rec = (st["styles"].get(answers.get("style")) or {}).get("defaults", {}).get("music")
        out = [{"label": v["label"] + (" (Recommended)" if k == rec else ""), "value": k, "description": f"library search: '{v['search']}', or an original synthesised score"} for k, v in st["music_moods"].items()]
        if out and not any("(Recommended)" in o["label"] for o in out):
            out[0]["label"] += " (Recommended)"
        out.sort(key=lambda o: "(Recommended)" not in o["label"])
        return out
    if src == "voices":
        lang = answers.get("language") or "en-US"
        delivery = answers.get("voice_energy") or "calm"
        vs = voices_cfg()["voices"].get(lang) or voices_cfg()["voices"]["en-US"]
        vs = sorted(vs, key=lambda v: delivery not in v.get("fits", []))
        return [{"label": v["label"].split(" - ")[0], "value": v["id"], "description": v["label"] + ("" if v["provider"] == "edge" else f" [{v['provider']}]")} for v in vs]
    return []


def _applies(q: dict, answers: dict) -> bool:
    w = q.get("when")
    if not w:
        return True
    for k, allowed in w.items():
        a = answers.get(k)
        vals = a if isinstance(a, list) else [a]
        if not any(str(x) in [str(y) for y in allowed] for x in vals):
            return False
    return True


def state(project: Path) -> tuple[dict, dict]:
    brief = load_yaml(project / "brief.yaml") or {}
    iv = brief.get("interview") or {}
    return brief, iv


def open_questions(project: Path) -> list[dict]:
    brief, iv = state(project)
    answers = iv.get("answers") or {}
    template = load_yaml(SKILL / "templates" / "brief.yaml") or {}
    rounds = []
    for r in bank()["rounds"]:
        qs = []
        for q in r["questions"]:
            if q["id"] in answers or not _applies(q, answers):
                continue
            item = {k: q[k] for k in ("id", "header", "question", "required") if k in q}
            item["multiSelect"] = bool(q.get("multi"))
            item["free_text"] = bool(q.get("free_text"))
            opts = _options(q, answers, project)
            if opts:
                item["options"] = opts
            prefill = _get(brief, q["maps_to"]) if q.get("maps_to") else None
            if prefill not in (None, "", [], {}) and prefill != _get(template, q["maps_to"]):   # template defaults are not answers
                item["from_prompt"] = prefill   # the prompt seemed to answer it: confirm, don't re-ask blindly
            qs.append(item)
        if qs:
            rounds.append({"round": r["id"], "title": r["title"], "note": r.get("note"), "questions": qs})
    return rounds


def _coerce(v):
    if isinstance(v, str):
        s = v.strip()
        if s[:1] in "[{" or s in ("true", "false", "null") or re.fullmatch(r"-?\d+(\.\d+)?", s):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                return v
    return v


def record(project: Path, answers: dict) -> dict:
    brief, iv = state(project)
    if iv.get("confirmed"):
        warn("the interview was already confirmed; recording a change the user asked for")
    qmap = {q["id"]: q for r in bank()["rounds"] for q in r["questions"]}
    store = iv.setdefault("answers", {})
    for k, v in answers.items():
        if k not in qmap:
            raise FishError(f"unknown interview question '{k}' (see config/interview.yaml)")
        q = qmap[k]
        v = _coerce(v)
        if q.get("multi") and isinstance(v, str):
            v = [x.strip() for x in v.split(",") if x.strip()]
        if q.get("secret"):
            _store_keys(str(v))
            store[k] = "(stored in .env)"
            continue
        store[k] = v
    brief["interview"] = iv
    apply(brief, project)
    save_yaml(project / "brief.yaml", brief)
    return store


def _store_keys(text: str) -> None:
    env = SKILL / ".env"
    have = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    keep = {ln.split("=", 1)[0]: ln for ln in have if "=" in ln}
    n = 0
    for ln in text.splitlines():
        m = re.match(r"\s*([A-Z][A-Z0-9_]{2,})\s*=\s*(\S+)\s*$", ln)
        if m:
            keep[m.group(1)] = f"{m.group(1)}={m.group(2)}"
            n += 1
    env.write_text("\n".join(keep.values()) + "\n", encoding="utf-8")
    log(f"stored {n} key(s) in {env} (gitignored; never printed)")


def apply(brief: dict, project: Path | None = None) -> dict:
    """Map answers into the brief + style defaults. Idempotent."""
    a = (brief.get("interview") or {}).get("answers") or {}
    st = styles()
    qmap = {q["id"]: q for r in bank()["rounds"] for q in r["questions"]}
    for k, v in a.items():
        m = qmap.get(k, {}).get("maps_to")
        if isinstance(v, str) and qmap.get(k, {}).get("free_text") and v.strip().lower() in ("none", "no", "n/a", "skip", "-"):
            v = None     # "no channel" must never become a badge that says "none"
        if k == "facts" and v:
            _apply_facts(brief, str(v))
        if m and v not in (None, ""):
            if k == "platforms":
                v = [p for x in (v if isinstance(v, list) else [v]) for p in str(x).split(",")]
            if k == "points" and isinstance(v, str):
                v = [p.strip(" -•\t") for p in v.splitlines() if p.strip(" -•\t")]
            if k == "references" and isinstance(v, str):
                v = [] if v.strip().lower() in ("none", "no", "") else re.findall(r"\S+", v)
            _set(brief, m, v)
    if a.get("topic") and not brief.get("title_set"):
        brief["title"] = re.split(r"[:.\n]", str(a["topic"]))[0].strip()[:70]
    cta_text = {"follow": "Follow for more", "comment": "Comment below"}.get(a.get("cta"))
    if cta_text and not (brief.get("cta") or {}).get("text"):
        brief.setdefault("cta", {})["text"] = cta_text
    if a.get("theme") in (None, "", "none"):
        if a.get("theme") == "none":
            brief.pop("theme", None)
    else:
        import themes
        if a["theme"] == "derived":
            import trends
            dv = trends.derived_theme(project) if project else None
            if not dv:
                raise FishError("theme 'derived' needs research/theme.json: run `fishvideo trends <dir> --derive-theme` first")
            brief["theme"] = dv["base"]
            brief["theme_overrides"] = {"colors": dict(dv["colors"])}
        else:
            brief["theme"] = a["theme"]
        themes.get(brief["theme"])
        pal_hex = a.get("palette") if isinstance(a.get("palette"), str) and "#" in a["palette"] else None
        if pal_hex:
            hexes = re.findall(r"#[0-9a-fA-F]{6}", pal_hex)
            brief["theme_overrides"] = {"colors": {k: h for k, h in zip(["bg", "ink", "accent", "accent2"], hexes)}}
    style = st["styles"].get(a.get("style") or brief.get("style") or "")
    d = (style or {}).get("defaults", {})
    if style:
        brief.setdefault("texture", d.get("texture"))
        brief["pacing"] = {**(brief.get("pacing") or {}), **(style.get("pacing") or {})}
        brief["motif"] = style.get("motif")
    pal = st["palettes"].get(a.get("palette") or d.get("palette") or "")
    if pal and pal.get("colors"):
        brief.setdefault("brand", {})["colors"] = dict(pal["colors"])
        mode = a.get("mode")
        brief["brand"]["mode"] = pal["mode"] if mode in (None, "auto") else mode
    elif isinstance(a.get("palette"), str) and "#" in a["palette"]:
        hexes = re.findall(r"#[0-9a-fA-F]{6}", a["palette"])
        if hexes:
            c = brief.setdefault("brand", {}).setdefault("colors", {})
            for key, h in zip(["bg", "ink", "accent", "accent2"], hexes):
                c[key] = h
    if brief.get("theme"):
        import themes
        themes.apply_to_brief(brief)           # the theme's colours, fonts, texture and caption look beat the style palette
    mood = st["music_moods"].get(a.get("music") or d.get("music") or "")
    if mood:
        brief["score"] = {**(brief.get("score") or {}), **{k: v for k, v in mood["score"].items() if k != "bpm"}}
        brief["tempo"] = {**(brief.get("tempo") or {}), "bpm": mood["score"].get("bpm", 120)}
        brief.setdefault("music", {})["search"] = mood["search"]
    if a.get("sfx"):
        brief.setdefault("sfx", {})["density"] = a["sfx"]
    if a.get("captions"):
        brief.setdefault("captions", {})["style"] = a["captions"]
    _apply_voice(brief, a)
    # Short vertical cuts: cut on beats, no dead air around or inside lines
    plats = brief.get("platforms") or []
    if plats and all(p in ("shorts", "reels", "tiktok") for p in plats) or (brief.get("length") or 999) <= 90:
        pac = brief.setdefault("pacing", {})
        for k, v in {"snap": "speech", "lead_in": 0.1, "tail": 0.15, "max_word_gap": 0.3}.items():
            pac.setdefault(k, v)
    return brief


def _apply_facts(brief: dict, text: str) -> None:
    """One fact per line: 'claim ... https://source'. Numbered facts become brief.facts; every link joins sources."""
    facts = brief.get("facts") or []
    sources = brief.get("sources") or []
    for line in text.splitlines():
        url = re.search(r"https?://\S+", line)
        if not url:
            continue
        src = url.group(0).rstrip(").,")
        claim = line.replace(url.group(0), "").strip(" -•()|\t")
        if src not in sources:
            sources.append(src)
        num = re.search(r"\d[\d,.]*\s?(%|[KMB]\\b|million|billion|trillion)?", claim)
        if num and not any(f.get("text") == claim for f in facts):
            facts.append({"text": claim, "value": num.group(0).strip(), "source": src})
    brief["facts"], brief["sources"] = facts, sources


def _apply_voice(brief: dict, a: dict) -> None:
    vc = voices_cfg()
    delivery = a.get("voice_energy")
    if delivery == "none" or (brief.get("style") and ((styles()["styles"].get(brief["style"]) or {}).get("defaults", {}).get("voice") == "none") and not a.get("voice")):
        brief.setdefault("voice", {})["provider"] = "none"
        return
    pick = a.get("voice")
    if not pick:
        return
    lang = a.get("language") or brief.get("language") or "en-US"
    allv = [v for vs in vc["voices"].values() for v in vs]
    v = next((x for x in allv if x["id"] == pick), None)
    pre = vc["delivery"].get(delivery or "calm", vc["delivery"]["calm"])
    voice = brief.setdefault("voice", {})
    voice["language"] = lang
    voice["post"] = pre["post"]
    voice["delivery"] = delivery or "calm"
    if v is None:  # "Other": a raw edge voice name or an ElevenLabs id
        v = {"provider": "elevenlabs" if re.fullmatch(r"[A-Za-z0-9]{20}", str(pick)) else "edge", "voice": pick}
    if v["provider"] == "elevenlabs":
        voice["provider"] = "elevenlabs"
        voice["elevenlabs"] = {**(voice.get("elevenlabs") or {}), "voice_id": v["voice"],
                               "voice_settings": {"stability": pre["stability"], "similarity_boost": 0.8, "style": pre["eleven_style"], "use_speaker_boost": True, "speed": pre["eleven_speed"]}}
        near = next((x for x in vc["voices"].get(lang, []) if x["provider"] == "edge"), None)
        if near:
            voice["fallback"] = {"provider": "edge-tts", "voice": near["voice"], "rate": pre["edge_rate"], "pitch": pre["edge_pitch"]}
    elif v["provider"] == "chatterbox":          # the recommended soft preset (config/voicelab.yaml -> chatterbox-soft)
        voice["provider"] = "chatterbox"
        voice["studio"] = {"gender": "male", "style": "chatterbox-soft", "pace": "natural"}
        voice["delivery"] = "soft"
        pac = brief.setdefault("pacing", {})
        pac.update({"max_word_gap": 0.9, "line_gap": 0.2})
        brief.setdefault("mix", {})["music_under_voice_db"] = -12
        return
    elif v["provider"] == "kokoro":
        voice["provider"] = "kokoro"
        voice["kokoro"] = {"voice": v["voice"], "speed": round(pre["wps"] / 2.9, 2)}
        near = next((x for x in vc["voices"].get(lang, []) if x["provider"] == "edge"), None)
        voice["fallback"] = {"provider": "edge-tts", "voice": (near or {}).get("voice", "en-US-AndrewMultilingualNeural"), "rate": pre["edge_rate"], "pitch": pre["edge_pitch"]}
    else:
        voice["provider"] = "edge-tts"
        voice["fallback"] = {"provider": "edge-tts", "voice": v["voice"], "rate": pre["edge_rate"], "pitch": pre["edge_pitch"]}
    brief.setdefault("pacing", {})["line_gap"] = pre["line_gap"]


def summary(project: Path) -> str:
    brief, iv = state(project)
    a = iv.get("answers") or {}
    st = styles()
    s = st["styles"].get(a.get("style"), {})
    lines = [f"# Brief summary: {brief.get('title') or a.get('topic', '')[:60]}", ""]
    for r in bank()["rounds"]:
        rows = [(q["header"], a[q["id"]]) for q in r["questions"] if q["id"] in a]
        if rows:
            lines.append(f"**{r['title']}**")
            lines += [f"- {h}: {json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v}" for h, v in rows]
            lines.append("")
    if s:
        lines += [f"Style bible: {s['look']}. Motif: {s['motif']}. A visual change every ~{s['pacing']['change_every']} s.", ""]
    c = (brief.get("brand") or {}).get("colors") or {}
    if c:
        lines.append("Colours: " + ", ".join(f"{k} {v}" for k, v in c.items() if k in ("bg", "ink", "accent", "accent2")))
    v = brief.get("voice") or {}
    if v.get("provider") in ("chatterbox", "kokoro") and v.get("studio"):
        stu = v["studio"]
        lines.append(f"Voice: {v['provider']} preset {stu.get('style')} ({stu.get('gender', 'male')}, pace {stu.get('pace', 'natural')}; Chatterbox default voice, one sentence at a time, seed 11); language {v.get('language')}")
    elif v.get("provider") == "none":
        lines.append("Voice: none (music and text)")
    else:
        lines.append(f"Voice: {v.get('provider')} {((v.get('fallback') or {}).get('voice') if v.get('provider') != 'elevenlabs' else (v.get('elevenlabs') or {}).get('voice_id'))} ({v.get('delivery', '')})")
    open_req = [q["id"] for rr in open_questions(project) for q in rr["questions"] if q.get("required")]
    lines.append("")
    lines.append("Open required questions: " + (", ".join(open_req) if open_req else "none"))
    return "\n".join(lines)


def confirm(project: Path) -> None:
    open_req = [q["id"] for rr in open_questions(project) for q in rr["questions"] if q.get("required")]
    if open_req:
        raise FishError(f"cannot confirm: required questions still open: {open_req}")
    brief, iv = state(project)
    iv["confirmed"] = True
    brief["interview"] = iv
    save_yaml(project / "brief.yaml", brief)
    log("interview confirmed: creation may start; no further questions until the final review")


def copy_problems(project: Path) -> list[str]:
    """Placeholder / stock / copied-example text in the storyboard."""
    sbf = project / "storyboard.yaml"
    if not sbf.exists():
        return ["no storyboard.yaml"]
    sb = load_yaml(sbf) or {}
    probs = []
    ex_lines = set()
    for exf in (SKILL / "examples").glob("*/storyboard.yaml"):
        for sc in (load_yaml(exf) or {}).get("scenes", []):
            for ln in (sc.get("say") if isinstance(sc.get("say"), list) else [sc.get("say")]):
                if ln and len(str(ln)) > 25:
                    ex_lines.add(re.sub(r"\W+", " ", str(ln)).strip().lower())
    for sc in sb.get("scenes", []):
        blob = json.dumps({"p": sc.get("params"), "say": sc.get("say")}, ensure_ascii=False)
        if PLACEHOLDER.search(blob):
            probs.append(f"{sc.get('id')}: placeholder text left ({PLACEHOLDER.search(blob).group(0)})")
        says = sc.get("say") if isinstance(sc.get("say"), list) else [sc.get("say")]
        for ln in says:
            if not ln:
                continue
            norm = re.sub(r"\W+", " ", str(ln)).strip().lower()
            if norm in ex_lines:
                probs.append(f"{sc.get('id')}: narration copied from an example storyboard: '{ln[:50]}'")
            for ph in STOCK_PHRASES:
                if ph.lower() in str(ln).lower() and len(str(ln)) < 60:
                    probs.append(f"{sc.get('id')}: stock scaffold phrase '{ph.strip()}' in narration: rewrite it")
    if not ((load_yaml(project / "brief.yaml") or {}).get("publish") or {}).get("titles"):
        probs.append("publishing copy: write brief.publish.titles (5 options), description, tags and hashtags")
    brief_ = load_yaml(project / "brief.yaml") or {}
    if not brief_.get("series"):
        for sc in sb.get("scenes", []):
            hit = SERIES.search(json.dumps({"p": sc.get("params"), "say": sc.get("say")}, ensure_ascii=False))
            if hit:
                probs.append(f"{sc.get('id')}: series text left in a single video ('{hit.group(0)}'): remove it, or set `series: true` in brief.yaml if this really is part of a series")
    th = sb.get("thumbnail") or {}
    if PLACEHOLDER.search(json.dumps(th)):
        probs.append("thumbnail: placeholder text left")
    return probs


def _example_media_hashes() -> dict:
    import hashlib
    out = {}
    for p in (SKILL / "examples").rglob("*"):
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4"):
            out[hashlib.sha256(p.read_bytes()).hexdigest()] = str(p.relative_to(SKILL / "examples"))
    return out


def example_problems(project: Path) -> list[str]:
    """Examples are past outputs: no example image or video file may appear inside a new project."""
    project = Path(project).resolve()
    if (SKILL / "examples").resolve() in project.parents:
        return []                                  # the examples themselves (some use custom scenes)
    probs = []
    import hashlib
    hashes = _example_media_hashes()
    if hashes:
        for p in list(project.glob("assets/**/*")) + list(project.glob("out/**/thumbnail*")):
            if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4"):
                h = hashlib.sha256(p.read_bytes()).hexdigest()
                if h in hashes:
                    probs.append(f"example file reused: {p.relative_to(project)} is identical to examples/{hashes[h]}: collect your own licensed images; examples are past outputs, never assets")
    probs += sameness_problems(project)
    return probs


def sameness_problems(project: Path) -> list[str]:
    """The scene-type sequence must not be identical to the recipe skeleton or to a bundled example: the direction must change something."""
    project = Path(project)
    sbf = project / "storyboard.yaml"
    if not sbf.exists():
        return []
    seq = [str(sc.get("type")) for sc in (load_yaml(sbf) or {}).get("scenes", [])]
    if len(seq) < 3:
        return []
    same = []
    recipe = (load_yaml(project / "brief.yaml") or {}).get("recipe") if (project / "brief.yaml").exists() else None
    if recipe:
        try:
            import recipes
            if seq == [str(sc.get("type")) for sc in recipes.storyboard(recipe).get("scenes", [])]:
                same.append(f"the `{recipe}` recipe skeleton")
        except FishError:
            pass
    for exf in sorted((SKILL / "examples").glob("**/storyboard.yaml")):
        if seq == [str(sc.get("type")) for sc in (load_yaml(exf) or {}).get("scenes", [])]:
            same.append(f"examples/{exf.parent.relative_to(SKILL / 'examples')}")
    if same:
        return [f"scene sequence is identical to {', '.join(same)}: apply the trend `direction` (research/trends.md) so the beat order, scene types or layouts change for this video"]
    return []


def gate(project: Path, stage: str = "render", force: bool = False) -> list[str]:
    project = ensure_project(project)
    brief, iv = state(project)
    errs = []
    open_req = [q["id"] for rr in open_questions(project) for q in rr["questions"] if q.get("required")]
    if open_req:
        errs.append(f"interview: required questions still open: {open_req} (run `fishvideo interview {project}` and ask them)")
    if not iv.get("confirmed"):
        errs.append("interview: not confirmed: read `fishvideo interview <dir> --summary` to the user, then `--confirm`")
    if brief.get("recipe") and stage in ("script", "render"):
        import gates
        errs += gates.budget_errors(project) if (project / "storyboard.yaml").exists() else []
    if (project / "storyboard.yaml").exists():
        errs += example_problems(project)
    if stage in ("script", "render"):
        import trends
        errs += trends.gate_problems(project)
        why = trends.unavailable_reason(project)
        if why:
            warn(f"trend research was UNAVAILABLE ({why}): built-in themes used; say so in the final report")
    if stage == "render":
        errs += copy_problems(project)
        try:
            import gates
            _m, fails = gates.check(project)
        except FishError as e:
            _m, fails = None, [str(e)]
        errs += [f"imagery gate ({brief.get('recipe') or 'default'}): {x}" for x in fails]       # every video: the default rule; opt-out only via visuals.mode: abstract on the user's request
        need = set((brief.get("approvals") or {}).get("required") or [])
        got = load_json(project / "approvals.json", default={}) if (project / "approvals.json").exists() else {}
        for n in ("storyboard", "stills"):
            if n in need and not got.get(n):
                errs.append(f"approval: the user asked to approve the {n} first (fishvideo approve <dir> {n})")
    if errs and force:
        for e in errs:
            warn(f"gate (forced): {e}")
        return []
    return errs


def approve(project: Path, what: str) -> None:
    f = project / "approvals.json"
    got = load_json(f, default={}) if f.exists() else {}
    import time
    got[what] = time.strftime("%Y-%m-%d %H:%M")
    save_json(f, got)
    log(f"approved: {what}")


def audition(project: Path) -> list[dict]:
    """The audition line in each shortlisted voice for the chosen language + delivery."""
    import voice as voicemod
    brief, iv = state(project)
    a = iv.get("answers") or {}
    lang = a.get("language") or brief.get("language") or "en-US"
    vc = voices_cfg()
    pre = vc["delivery"].get(a.get("voice_energy") or "calm", vc["delivery"]["calm"])
    line = vc["audition_line"]["hi" if lang.startswith("hi") else "en"]
    out = project / "build" / "auditions"
    out.mkdir(parents=True, exist_ok=True)
    res = []
    for v in vc["voices"].get(lang, vc["voices"]["en-US"]):
        f = out / f"{v['id']}.mp3"
        try:
            if v["provider"] == "edge":
                audio, _ = voicemod.edge(line, {"voice": v["voice"], "rate": pre["edge_rate"], "pitch": pre["edge_pitch"]})
            elif v["provider"] == "elevenlabs":
                key = secret("ELEVENLABS_API_KEY", project)
                if not key:
                    res.append({"id": v["id"], "skipped": "no ELEVENLABS_API_KEY"})
                    continue
                audio, _ = voicemod.elevenlabs(line, {"elevenlabs": {"voice_id": v["voice"], "model_id": "eleven_multilingual_v2",
                                                                     "voice_settings": {"stability": pre["stability"], "similarity_boost": 0.8, "style": pre["eleven_style"], "use_speaker_boost": True}}}, key)
            elif v["provider"] == "kokoro":
                audio = voicemod.kokoro_audio(line, {"voice": v["voice"], "speed": round(pre["wps"] / 2.9, 2)})
            elif v["provider"] == "chatterbox":
                import voicelab
                if not voicelab.engine_ready("chatterbox"):
                    res.append({"id": v["id"], "skipped": "Chatterbox is not installed: run `fishvideo voice setup --engine chatterbox` (one command), then audition again. Not substituted by another voice."})
                    continue
                f = out / f"{v['id']}.wav"
                voicelab.say(line, f, "chatterbox", {"gender": "male", "style": "chatterbox-soft"}, lang, out / "_chatterbox")
                res.append({"id": v["id"], "label": v["label"], "file": str(f)})
                continue
            else:
                continue
            f.write_bytes(audio)
            res.append({"id": v["id"], "label": v["label"], "file": str(f)})
        except Exception as e:  # noqa: BLE001 - an audition failing must not stop the others
            res.append({"id": v["id"], "skipped": str(e)[:120]})
    save_json(out / "auditions.json", res)
    for r in res:
        log(f"  {r['id']:<16} {r.get('file') or 'skipped: ' + r.get('skipped', '')}")
    return res


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--answers")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args(argv)
    project = ensure_project(a.project)
    ans = {}
    if a.answers:
        ans.update(json.loads(Path(a.answers).read_text(encoding="utf-8")))
    for kv in a.set:
        k, _, v = kv.partition("=")
        ans[k.strip()] = v
    if ans:
        record(project, ans)
    if a.confirm:
        confirm(project)
    if a.summary:
        print(summary(project))
    elif not a.confirm:
        print(json.dumps(open_questions(project), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    main_guard(cli)
