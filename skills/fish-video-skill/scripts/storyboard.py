"""Storyboard: scaffold, validate, time and lint the edit.

    python scripts/storyboard.py <project>                 validate + resolve timelines for every platform
    python scripts/storyboard.py <project> --scaffold      write storyboard.yaml from brief + research (if missing)
    python scripts/storyboard.py <project> --script        also write script.md (the readable narration script)

storyboard.yaml is the single source of truth for the edit: an ordered list
of scenes, each with a `type` from the scene library, its `params`, and the
narration it carries (`say`). Timing is derived, not typed: every scene
gets as many 2-second bars (120 BPM) as its narration and its animation
need, so every cut lands on a bar line and the music can follow.

Outputs (build/):
    timeline-<platform>.json   what the stage renders and the mixer places
    captures.json              the live shots capture.mjs records
    script.md                  the narration as a reading script (--script)
"""
from __future__ import annotations

import argparse
import math
import json
import re
from pathlib import Path

from fvcore import (FishError, deep_merge, ensure_project, load_json, load_yaml, log, main_guard, mmss,
                    project_config, save_json, save_yaml, sha1, slugify, warn)
from captions import chunk_words
import themes
import score as score_mod

SCENE_TYPES = {"title", "kinetic", "bullets", "stat", "chart", "diagram", "whiteboard", "steps", "quote",
               "compare", "terminal", "tour", "image", "end", "thumbnail",
               # looks: paper collage, kinetic studio, neon / geometric, footage, screen-explainer steps
               "collage", "split", "cone", "coinflip", "orbit", "neonline", "glowshape", "tunnel", "ringbloom",
               "footage", "stepcard", "meme",
               # long-format roadmap explainers
               "roadmap", "pile",
               # image-led and word-synced scenes (scenes/story.js)
               "story", "statement", "cards", "flow", "site", "bold"}
TRANSITIONS = {"fade", "cut", "wipe", "zoom", "flash", "defocus", "flip", "flood", "dip", "iris", "through", "world", "match"}
CAPTION_STYLES = {"pop", "karaoke", "minimal", "none"}
TEXTURES = {"paper", "grain", "clean", "grid", "blueprint", "halftone", "scanlines", "notebook", "dots", "sunburst", "stripes", "film"}
# scene-level camera rig fields, passed through to the timeline (see references/scene-catalogue.md, Camera)
CAMERA_KEYS = ("camera", "camera_from", "camera_shake", "camera_shake_on", "camera_blend", "dof", "dof_max", "dof_text", "accent", "carry", "lead")
PAIR = re.compile(r"\{([^|}]+)\|([^}]+)\}")


# ------------------------------------------------------------------ narration markup
def apply_pronunciations(text: str, pron: dict | None) -> str:
    """Wrap known words as {shown|spoken} pairs (whole words, outside existing pairs)."""
    if not pron:
        return text
    parts = re.split(r"(\{[^}]*\})", text)
    for i, part in enumerate(parts):
        if part.startswith("{"):
            continue
        for shown, spoken in sorted(pron.items(), key=lambda kv: -len(kv[0])):
            part = re.sub(rf"(?<![\w{{|]){re.escape(shown)}(?![\w|}}])", "{" + shown + "|" + spoken + "}", part)
        parts[i] = part
    return "".join(parts)


def parse_say(text: str) -> tuple[str, str, list[dict]]:
    """'{GGUF|G G U F} file' -> (display, spoken, units).

    display is what captions show, spoken is what the TTS reads; units are
    caption words [{w, s, e}] with character ranges in the spoken string, so
    word timings from the TTS can be mapped back to the displayed words.
    """
    say, disp, units = "", "", []
    pos = 0

    def plain(chunk: str):
        nonlocal say, disp
        base = len(say)
        say += chunk
        disp += chunk
        for m in re.finditer(r"\S+", chunk):
            units.append({"w": m.group(0), "s": base + m.start(), "e": base + m.end()})

    for m in PAIR.finditer(text):
        plain(text[pos:m.start()])
        s = len(say)
        say += m.group(2)
        disp += m.group(1)
        units.append({"w": m.group(1), "s": s, "e": len(say)})
        pos = m.end()
    plain(text[pos:])
    merged: list[dict] = []
    for u in units:
        if merged and not re.search(r"\w", u["w"]):
            merged[-1]["w"] += ("" if u["s"] == merged[-1]["e"] else " ") + u["w"]
            merged[-1]["e"] = u["e"]
        elif merged and u["s"] == merged[-1]["e"]:
            merged[-1]["w"] += u["w"]
            merged[-1]["e"] = u["e"]
        else:
            merged.append(dict(u))
    return disp, say, merged


def map_units(units: list[dict], words: list[dict]) -> list[dict]:
    """TTS words [{text, start, end, char}] -> units with clip-relative t0/t1."""
    out, last = [], 0.0
    for u in units:
        hit = [w for w in words if u["s"] <= w["char"] < u["e"]]
        if hit:
            t0, t1 = min(w["start"] for w in hit), max(w["end"] for w in hit)
        else:
            t0 = t1 = last
        last = t1
        out.append({"w": u["w"], "t0": round(t0, 3), "t1": round(t1, 3)})
    return out


def estimate_units(units: list[dict], seconds: float) -> list[dict]:
    """Spread units over `seconds` in proportion to their length (pre-TTS estimate)."""
    weights = [max(2, len(u["w"])) + 2 for u in units]
    total = sum(weights) or 1
    t, out = 0.0, []
    for u, w in zip(units, weights):
        d = seconds * w / total
        out.append({"w": u["w"], "t0": round(t, 3), "t1": round(t + d * 0.92, 3)})
        t += d
    return out


def words_per_minute(cfg: dict, lang: str) -> float:
    w = cfg["pacing"]["wpm"]
    return float(w.get(lang) or w.get(lang.split("-")[0]) or w["default"])


def estimate_seconds(spoken: str, wpm: float) -> float:
    words = len(re.findall(r"[\w'’-]+", spoken))
    pauses = len(re.findall(r"[,;:—–]", spoken)) * 0.12 + len(re.findall(r"[.!?…]", spoken)) * 0.25
    return round(words / wpm * 60 + pauses, 2)


MAX_PAUSE = 0.8                      # a planned pause (`pause:` on a line) for a reveal or punchline, never longer
LINE_TAGS = ("hook", "setup", "reveal", "punchline", "beat")


def line_gaps(lines: list[dict]) -> dict:
    """Silence between neighbouring narration lines in seconds (video time), with the median and maximum."""
    g = [round(b["at"] - (a["at"] + a["dur"]), 3) for a, b in zip(lines, lines[1:])]
    s = sorted(g)
    med = (s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2) if s else 0.0
    return {"median": round(med, 3), "max": max(g) if g else 0.0, "values": g}


def speech_pacing(pac: dict) -> dict:
    """Narration drives time: the next line starts 0.15-0.35 s after the last, whatever the format."""
    c = lambda v, lo, hi: min(hi, max(lo, float(v)))
    return {"lead": c(pac.get("lead_in", 0.1), 0.05, 0.15), "tail": c(pac.get("tail", 0.15), 0.1, 0.2), "gap": c(pac.get("line_gap", 0.25), 0.15, 0.35)}


def scene_lines(scene: dict, pron: dict | None = None) -> list[dict]:
    """The narration lines of a scene: [{id, text, display, say, units, at?}]."""
    raw = scene.get("say") or []
    if isinstance(raw, str):
        raw = [raw]
    out = []
    for k, ln in enumerate(raw):
        at, pause, tag = None, 0.0, None
        if isinstance(ln, dict):
            at, pause, tag, ln = ln.get("at"), ln.get("pause") or 0.0, ln.get("tag"), ln.get("text", "")
        text = apply_pronunciations(str(ln).strip(), pron)
        if not text:
            continue
        disp, say, units = parse_say(text)
        out.append({"id": f"{scene['id']}-{k + 1}", "text": text, "display": disp, "say": say, "units": units, "at": at,
                    "pause": min(max(float(pause), 0.0), MAX_PAUSE), "tag": tag if tag in LINE_TAGS else None})
    return out


# ------------------------------------------------------------------ minimum on-screen time per scene
def min_visual(scene: dict, cfg: dict, beat: float, shots: dict) -> float:
    t, p = scene["type"], scene.get("params") or {}
    base = float(cfg["pacing"]["min_scene"].get(t, 3.0))
    n = lambda k: len(p.get(k) or [])
    if t == "bullets":
        base = max(base, beat * 2 + n("items") * 1.1 + 1.2)
    elif t == "chart":
        base = max(base, beat * (2 + n("data")) + 1.8)
    elif t == "diagram":
        base = max(base, beat * 2 + n("nodes") * 1.6 + 1.5)
    elif t == "steps":
        base = max(base, beat * (2 + 2 * n("items")) + 1.5)
    elif t == "kinetic":
        base = max(base, beat * (0.5 + 2 * max(1, n("lines"))) + 1.2)
    elif t == "whiteboard":
        items = p.get("items")
        if items:
            last = max(((it.get("at", 1) + it.get("dur", 1.2)) for it in items), default=2)
        else:
            last = 1 + 3 * max(1, n("flow"))
        base = max(base, last * beat + (2.2 if p.get("take") else 1.2))
    elif t == "terminal":
        cps, tt = p.get("cps", 16), beat * 2
        for ln in p.get("lines") or []:
            tt += (len(ln["cmd"]) / cps + beat * 1.5) if "cmd" in ln else beat * 0.5
        base = max(base, tt + 1.2 + (1.0 if p.get("chips") else 0))
    elif t == "compare":
        nl, nr = len((p.get("left") or {}).get("items") or []), len((p.get("right") or {}).get("items") or [])
        base = max(base, beat * (3 + nl * 0.5 + nr) + 1.5)
    elif t == "stepcard":
        base = float(cfg["pacing"]["min_scene"].get(t, 1.8))
    elif t == "meme":
        base = max(base, beat * (3 + 2 * (1 if p.get("inset") else 0)) + 1.6)
    elif t == "tour":
        meta = shots.get(p.get("shot"))
        if meta:
            fps, sp = meta.get("fps", 30), p.get("speed", 1) or 1
            f0 = p.get("from", 0)
            f0 = meta.get("marks", {}).get(f0, 0) if isinstance(f0, str) else f0
            scene["_footage"] = max(0.0, (meta["count"] - f0) / (fps * sp))
    return base


DEFAULT_ENERGY = {"title": 2, "kinetic": 1, "end": 0, "tour": 3, "whiteboard": 2, "diagram": 2, "chart": 2, "stat": 3,
                  "bullets": 2, "steps": 2, "terminal": 2, "quote": 1, "compare": 2, "image": 1, "thumbnail": 0,
                  "collage": 2, "split": 3, "cone": 1, "coinflip": 3, "orbit": 2, "neonline": 3, "glowshape": 2,
                  "tunnel": 3, "ringbloom": 3, "footage": 2, "stepcard": 2, "meme": 3}


# ------------------------------------------------------------------ validation
def validate(sb: dict, cfg: dict | None = None) -> tuple[list[str], list[str]]:
    """(errors, warnings) for a storyboard dict."""
    errors, warns = [], []
    scenes = sb.get("scenes") or []
    if not scenes:
        errors.append("storyboard has no scenes")
    ids = set()
    shot_ids = {c.get("id") for c in sb.get("captures") or []}
    for i, s in enumerate(scenes):
        where = f"scene {i + 1} ({s.get('id', '?')})"
        if not s.get("id"):
            errors.append(f"{where}: missing id")
        elif s["id"] in ids:
            errors.append(f"{where}: duplicate id")
        ids.add(s.get("id"))
        if s.get("type") not in SCENE_TYPES and not sb.get("custom_scenes"):
            errors.append(f"{where}: unknown type {s.get('type')!r} (one of {', '.join(sorted(SCENE_TYPES))})")
        if s.get("transition") and s["transition"] not in TRANSITIONS:
            errors.append(f"{where}: transition must be one of {sorted(TRANSITIONS)}")
        p = s.get("params") or {}
        if s.get("type") == "tour" and p.get("shot") not in shot_ids:
            errors.append(f"{where}: tour shot {p.get('shot')!r} is not in captures")
        if s.get("type") == "stat" and not p.get("source"):
            warns.append(f"{where}: a stat with no source — every number needs one")
        if s.get("type") == "chart" and not p.get("source"):
            warns.append(f"{where}: a chart with no source")
        if s.get("type") == "meme":
            if not (p.get("src") or p.get("clip")):
                errors.append(f"{where}: a meme scene needs `src` (a picture under the project) or `clip` (cut with `memes cut`)")
            for nm in (p.get("clip"), (p.get("inset") or {}).get("clip")):
                if nm and (not isinstance(nm, str) or re.sub(r"[^A-Za-z0-9._-]+", "-", nm).strip("-.") != nm or ".." in nm):
                    errors.append(f"{where}: clip name {nm!r} must be a plain name (letters, digits, . _ -): the id you gave `memes cut`")
            for ref in (p.get("src"), (p.get("inset") or {}).get("src")):
                if ref and (str(ref).startswith(("/", "\\")) or ".." in Path(str(ref)).parts or re.match(r"^[a-z]+:", str(ref), re.I)):
                    errors.append(f"{where}: meme picture {ref!r} must be a path inside the project (for example assets/meme/x.png)")
        blob = repr(p) + repr(s.get("say"))
        if re.search(r"\bTODO\b|\bTBD\b|lorem ipsum", blob, re.I):
            warns.append(f"{where}: contains TODO/placeholder text")
    no_end = sb.get("end_card") is False
    rn = ((cfg or {}).get("brief") or {}).get("recipe")
    if rn and not no_end:
        try:
            import recipes
            no_end = recipes.get(rn).get("end_card") is False        # story and bold Shorts end on an open loop or a rule, not a logo card
        except Exception:                                            # noqa: BLE001 - an unknown recipe is reported elsewhere
            pass
    if scenes and scenes[-1].get("type") != "end" and not no_end:
        warns.append("the last scene is not an `end` card (brand + call to action). Recipes whose last beat is an open loop set `end_card: false`")
    return errors, warns


# ------------------------------------------------------------------ timeline
def _meme_params(project: Path, p: dict) -> dict:
    """A meme scene names its clip; the frame count and rate come from the clip's own meta.json (an explicit value wins)."""
    def fill(q: dict) -> dict:
        mj = Path(project) / "build" / "clips" / str(q.get("clip") or "") / "meta.json"
        if q.get("clip") and mj.is_file():
            meta = load_json(mj)
            return {"frames": meta.get("frames"), "fps": meta.get("fps"), **q}
        return q
    p = fill(dict(p))
    if isinstance(p.get("inset"), dict):
        p["inset"] = fill(dict(p["inset"]))
    return p


def resolve(project: Path, platform: str, cfg: dict, sb: dict, clips: dict | None = None) -> dict:
    """Resolve one platform's timeline: bars, absolute times, voice placement, captions, energy."""
    brief = cfg["brief"]
    prof = cfg["platforms"].get(platform)
    if not prof:
        raise FishError(f"unknown platform {platform!r} (one of {', '.join(cfg['platforms'])})")
    pac = cfg["pacing"]
    snap = pac.get("snap") or "speech"
    snap = "speech" if snap == "beat" else snap          # "beat" was the Shorts-only form of the same idea
    explicit_score = deep_merge(brief.get("score") or {}, sb.get("score") or {})
    score_d = score_mod.derive(project, brief, explicit_score)
    bpm = float(sb.get("bpm") or (score_d.get("bpm") if snap == "speech" else None) or cfg["tempo"]["bpm"])
    bpb = int(cfg["tempo"]["beats_per_bar"])
    beat, bar = 60.0 / bpm, 60.0 / bpm * bpb
    sp = speech_pacing(pac) if snap == "speech" else None
    lead_in, tail_s, line_gap = (sp["lead"], sp["tail"], sp["gap"]) if sp else (pac["lead_in"], pac["tail"], pac["line_gap"])
    lang = brief.get("language", "en-IN")
    wpm = words_per_minute(cfg, lang)
    pron = (brief.get("voice") or {}).get("pronunciations") or {}
    clips = clips or {}
    shots = {}
    for c in sb.get("captures") or []:
        mf = Path(project) / "build" / "cap" / c["id"] / "meta.json"
        if mf.exists():
            shots[c["id"]] = load_json(mf)
    voice_on = (brief.get("voice") or {}).get("provider", cfg["voice"]["provider"]) != "none"

    scenes = [s for s in sb["scenes"] if not s.get("platforms") or platform in s["platforms"]]
    if platform == "thumbnail":
        thumb = dict(sb.get("thumbnail") or {"title": brief.get("title", "")})
        # no hero named: borrow the film's first real picture (a cut-out first)
        if not (thumb.get("image") or thumb.get("hero") or thumb.get("shot")):
            pics = [(it.get("kind") == "cutout", it["src"]) for sc in sb.get("scenes", []) for it in [*((sc.get("params") or {}).get("items") or []), (sc.get("params") or {})] if isinstance(it, dict) and it.get("src")]
            if pics:
                thumb["image"] = next((src for cut, src in pics if cut), pics[0][1])
        scenes = [{"id": "thumb", "type": "thumbnail", "params": thumb}]
    out_scenes, voice_lines, all_words, music = [], [], [], []
    t_bar = 0
    for i, s in enumerate(scenes):
        s = dict(s)
        lines = scene_lines(s, pron) if voice_on and platform != "thumbnail" else []
        local = lead_in
        placed = []
        for ln in lines:
            clip = clips.get(ln["id"])
            fresh = clip and clip.get("say") == ln["say"]
            if clip and not fresh:
                warn(f"{ln['id']}: narration changed since the voice was made; re-run `fishvideo voice`")
            dur = clip["speech_end"] if fresh else estimate_seconds(ln["say"], wpm)
            start = float(ln["at"]) * beat if ln.get("at") is not None else local + float(ln.get("pause") or 0)
            units = map_units(ln["units"], clip["words"]) if fresh else estimate_units(ln["units"], dur)
            placed.append({**ln, "local": start, "dur": dur, "clip": clip if fresh else None, "units_rel": units})
            local = start + dur + line_gap
        speech_end = (placed[-1]["local"] + placed[-1]["dur"] + tail_s) if placed else 0
        need = max(min_visual(s, cfg, beat, shots), speech_end)
        if placed and snap == "speech":
            # the line sets the length: animation minimums and recipe slots made dead air after short lines
            need = max(speech_end, min(need, speech_end + float(pac.get("max_hold", 0.25))))   # hold a picture at most 0.25 s past the last word
        ts = float((s.get("ts") or {}).get(platform, 1) if isinstance(s.get("ts"), dict) else s.get("ts") or 1)
        if placed:
            ts = 1.0  # narrated scenes play in real time, or the voice drifts off the picture
        # pacing.snap: "bar" (cuts on 2 s bars, long formats) or "beat" (Shorts: no dead air after a line)
        if s.get("bars"):
            bars = s["bars"]
        elif snap == "speech" and placed:
            bars = round(max(0.25, need / ts / bar), 4)        # follows the speech exactly; the music moves to it, not the voice to the music
        else:
            bars = max(1, math.ceil(need / ts / bar - 1e-6))
        if s.get("bars_min") and not (snap == "speech" and placed):   # a recipe slot: only a silent beat or the legacy bar mode keeps its minimum
            bars = max(bars, s["bars_min"])
        if s.get("bars") and need / ts > bars * bar + 0.01:
            warn(f"{platform}: scene {s['id']} needs {need:.1f}s but has {bars} bars ({bars * bar:.1f}s)")
        if s.get("_footage") is not None and bars * bar * ts > s["_footage"] + 0.05:
            warn(f"{platform}: tour {s['id']} runs {bars * bar * ts:.1f}s but the capture has only {s['_footage']:.1f}s at speed {(s.get('params') or {}).get('speed', 1)}; it will hold on the last frame")
        t0, t1 = t_bar * bar, (t_bar + bars) * bar
        energy = s.get("energy", DEFAULT_ENERGY.get(s["type"], 2))
        if i == 0 and "energy" not in s:
            energy = 1
        music.append([t_bar, energy])
        if s["type"] == "meme":
            s["params"] = _meme_params(project, s.get("params") or {})
        out_scenes.append({"id": s["id"], "type": s["type"], "t0": round(t0, 4), "t1": round(t1, 4), "bars": bars, "ts": ts,
                           "params": {**(s.get("params") or {}), **({"cues": s["cues"]} if s.get("cues") else {}), **_px_params(project, s)}, "chapter": s.get("chapter"), "transition": s.get("transition", "fade" if i else "cut"),
                           "hud": s.get("hud"), "energy": energy,
                           **{k: s[k] for k in CAMERA_KEYS if s.get(k) is not None}})
        for pl in placed:
            at = t0 + pl["local"]
            words = [{"w": u["w"], "t0": round(at + u["t0"], 3), "t1": round(at + u["t1"], 3)} for u in pl["units_rel"]]
            all_words.extend(words)
            vl = {"id": pl["id"], "scene": s["id"], "at": round(at, 3), "display": pl["display"], "say": pl["say"], "dur": round(pl["dur"], 3), "estimated": pl["clip"] is None,
                  **({"tag": pl["tag"]} if pl.get("tag") else {}), **({"pause": pl["pause"]} if pl.get("pause") else {})}
            if pl["clip"]:
                vl.update({"wav": pl["clip"]["wav"], "offset": pl["clip"].get("speech_start", 0.0), "provider": pl["clip"].get("provider")})
            voice_lines.append(vl)
        # `caption:` on-screen captions for a scene with no narration (silent cuts, music-only Shorts)
        if not placed and s.get("caption") and platform != "thumbnail":
            for ln in scene_lines({"id": s["id"] + "-cap", "say": s["caption"]}):
                start = float(ln["at"]) * beat if ln.get("at") is not None else lead_in
                dur = min(estimate_seconds(ln["say"], wpm) * 1.15, max(0.6, bars * bar * ts - start - 0.3))
                all_words.extend({"w": u["w"], "t0": round(t0 + start + u["t0"], 3), "t1": round(t0 + start + u["t1"], 3)}
                                 for u in estimate_units(ln["units"], dur))
        t_bar += bars
    if platform != "thumbnail":
        music.append([t_bar, 0])
    total = t_bar * bar
    capcfg = deep_merge(cfg["captions"], prof.get("captions") or {})
    burn_pref = (brief.get("captions") or {}).get("burn", "auto")
    burn = prof.get("burn_captions", False) if burn_pref in ("auto", None) else bool(burn_pref)
    cap_style = (sb.get("captions") or {}).get("style") or (brief.get("captions") or {}).get("style") or "karaoke"
    if cap_style not in CAPTION_STYLES:
        warn(f"captions.style {cap_style!r} is not one of {sorted(CAPTION_STYLES)}; using karaoke")
        cap_style = "karaoke"
    # sfx: {density: rich|standard|minimal, ...} (a bare string is the density); read by the stage and sfx.py
    sfx_raw = sb.get("sfx") or brief.get("sfx") or {}
    sfx_cfg = dict(sfx_raw) if isinstance(sfx_raw, dict) else {"density": str(sfx_raw)}
    texture = sb.get("texture") or brief.get("texture")
    if texture and texture not in TEXTURES:
        warn(f"texture {texture!r} is not one of {sorted(TEXTURES)}; ignoring it")
        texture = None
    cues = chunk_words(all_words, capcfg["max_chars"], capcfg["max_lines"], min_dur=capcfg.get("min_cue", 0.9))
    for q in cues:      # a cue's linger must never run past the end of the video
        q["end"] = min(q["end"], total)
    brand = dict(brief.get("brand") or {})
    brand["name"] = brand.get("name") or brief.get("title", "")
    theme = {"colors": brand.get("colors") or {}, "fonts": brand.get("fonts") or {}, "font_files": brand.get("font_files") or [], "mode": brand.get("mode", "light")}
    th = themes.resolve(brief)            # `theme: <id>` in the brief: colours, fonts, texture, layout tokens and caption look (config/themes.yaml)
    if th:
        theme = {**theme, "colors": th["colors"], "fonts": th["fonts"], "mode": th["mode"], "layout": th["layout"], "captions": th["captions"], "id": th["id"]}
        if th["texture"] and not texture:
            texture = th["texture"]
        if th["caption_style"] and not (sb.get("captions") or {}).get("style") and (brief.get("captions") or {}).get("style") in (None, "karaoke"):
            cap_style = th["caption_style"]
    used_shots = sorted({(s["params"] or {}).get("shot") for s in out_scenes if s["type"] in ("tour", "thumbnail") and (s["params"] or {}).get("shot") in shots})
    score = deep_merge(cfg["score"], {k: v for k, v in score_d.items() if k != "fixed"})
    return {
        "platform": platform, "label": prof.get("label", platform), "W": prof["W"], "H": prof["H"], "fps": prof.get("fps", 30),
        "bpm": bpm, "beats_per_bar": bpb, "snap": snap, "gaps": line_gaps(voice_lines), "bars": t_bar, "duration": round(total, 4), "frames": int(round(total * prof.get("fps", 30))),
        "lang": brief.get("language", "en-IN"), "title": brief.get("title", ""),
        "theme": theme, "brand": {**{k: brand.get(k, "") for k in ("name", "url", "logo", "tagline")}, "explicit_name": bool((brief.get("brand") or {}).get("name"))},
        "style": sb.get("style") or brief.get("style"), "anchor": sb.get("anchor"),
        "safe": prof.get("safe"), "hud": sb.get("hud", {"chapter": True, "rail": True}), "grain": sb.get("grain", True),
        "background": sb.get("background", "dots"), "legibility": {"min_px": prof.get("min_text_px", 22)},
        "captions": {"burn": burn, "max_chars": capcfg["max_chars"], "max_lines": capcfg["max_lines"], "cues": cues,
                     "style": cap_style, "delivery": (brief.get("voice") or {}).get("delivery")},
        "texture": texture, "sfx": sfx_cfg,
        "scenes": out_scenes, "music": music, "score": score, "shots": used_shots,
        "custom_scenes": sb.get("custom_scenes") or [], "voice_lines": voice_lines, "words": all_words,
        "max_seconds": prof.get("max_seconds"),
    }


def captures_spec(brief: dict, sb: dict) -> dict:
    """Normalise storyboard captures (+ brief.website defaults) for capture.mjs."""
    web = brief.get("website") or {}
    shots = []
    for c in sb.get("captures") or []:
        c = dict(c)
        c.setdefault("theme", web.get("theme", "light"))
        if web.get("hide"):
            c["hide"] = list(c.get("hide") or []) + list(web["hide"])
        if web.get("storage"):
            c["storage"] = {**web["storage"], **(c.get("storage") or {})}
        if not c.get("actions") and not c.get("auto"):
            c["auto"] = {"seconds": 8}
        shots.append(c)
    return {"shots": shots}


def platforms_of(cfg: dict) -> list[str]:
    plats = list(cfg["brief"].get("platforms") or ["youtube"])
    for p in plats:
        if p not in cfg["platforms"]:
            raise FishError(f"unknown platform {p!r} in brief.platforms")
    return plats


def custom_scene_overrides(project: Path, sb: dict) -> list[str]:
    """Warnings for project scene files that assign a built-in scene name (`S.pile = ...`, `SCENES["roadmap"] = ...`).
    The project file loads last, so it silently replaces the built-in everywhere in the video. Source scan, so a heuristic."""
    out = []
    for rel in sb.get("custom_scenes") or []:
        f = project / str(rel).lstrip("/")
        if not f.is_file():
            continue
        src = f.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"""\b(?:S|SCENES|window\.SCENES)\s*(?:\.\s*([A-Za-z_$][\w$]*)|\[\s*["']([^"']+)["']\s*\])\s*=(?!=)""", src):
            name = m.group(1) or m.group(2)
            if name in SCENE_TYPES:
                out.append(f"{rel}: defines scene {name!r}, which REPLACES the built-in {name!r} scene for every scene of that type "
                           f"in this video. Rename it if that is not intended.")
    return sorted(set(out))


def image_sizes(project: Path, params: dict) -> dict:
    """{path: [w, h]} for the pictures a scene shows (so the stage can decide between full-bleed and a framed card without decoding first)."""
    out = {}
    refs = [params.get("src")] + [x.get("src") for x in (params.get("srcs") or []) if isinstance(x, dict)]
    for r in refs:
        if isinstance(r, str) and r.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and (Path(project) / r).exists():
            try:
                from PIL import Image
                with Image.open(Path(project) / r) as im:
                    out[r] = list(im.size)
            except Exception:                                     # noqa: BLE001 - an unreadable file is reported by the gate
                pass
    return out


def _ground_copies(project: Path, srcs: list[str]) -> dict:
    """Small copies (480 px) of the pictures for the blurred backdrop: blurring a 2400 px original wastes memory and has crashed the renderer's browser."""
    out = {}
    for r in srcs:
        f = Path(project) / r
        if not f.exists():
            continue
        dst = Path(project) / "assets" / "_ground" / (re.sub(r"[^\w.-]+", "_", r) + ".jpg")
        try:
            if not dst.exists() or dst.stat().st_mtime < f.stat().st_mtime:
                from PIL import Image
                dst.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(f) as im:
                    k = 480 / max(im.size)
                    (im.convert("RGB").resize((max(1, round(im.width * k)), max(1, round(im.height * k)))) if k < 1 else im.convert("RGB")).save(dst, quality=85)
            out[r] = str(dst.relative_to(project)).replace("\\", "/")
        except Exception:                                         # noqa: BLE001 - fall back to the original
            pass
    return out


def _px_params(project: Path, s: dict) -> dict:
    if s.get("type") not in ("story", "image", "statement"):
        return {}
    px = image_sizes(project, s.get("params") or {})
    return {"_px": px, "_ground": _ground_copies(project, list(px))} if px else {}


def build(project: Path, *, quiet: bool = False) -> dict:
    """Validate the storyboard and write every timeline + captures.json."""
    project = ensure_project(project)
    cfg = project_config(project)
    sbf = project / "storyboard.yaml"
    if not sbf.exists():
        raise FishError("no storyboard.yaml: run `fishvideo script` (scaffold) or write one from templates/storyboard.yaml")
    sb = load_yaml(sbf)
    errors, warns = validate(sb, cfg)
    warns += custom_scene_overrides(project, sb)
    for w in warns:
        warn(w)
    if errors:
        raise FishError("storyboard is invalid:\n  " + "\n  ".join(errors))
    clips = load_json(project / "build" / "voice" / "clips.json", default={}).get("clips", {}) if (project / "build" / "voice" / "clips.json").exists() else {}
    save_json(project / "build" / "captures.json", captures_spec(cfg["brief"], sb))
    summary = {}
    for p in platforms_of(cfg) + ["thumbnail"]:
        tl = resolve(project, p, cfg, sb, clips)
        save_json(project / "build" / f"timeline-{p}.json", tl)
        if p != "thumbnail":
            est = sum(1 for v in tl["voice_lines"] if v["estimated"])
            summary[p] = {"duration": tl["duration"], "bars": tl["bars"], "scenes": len(tl["scenes"]), "lines": len(tl["voice_lines"]), "estimated_lines": est, "captions": len(tl["captions"]["cues"])}
            if tl.get("max_seconds") and tl["duration"] > tl["max_seconds"]:
                warn(f"{p}: {tl['duration']:.0f}s is longer than the platform limit of {tl['max_seconds']}s; cut scenes with `platforms:`")
            target = cfg["brief"].get("length")
            if target and p == platforms_of(cfg)[0] and abs(tl["duration"] - float(target)) > max(6, float(target) * 0.15):
                warn(f"{p}: runs {tl['duration']:.0f}s against a target of {float(target):.0f}s")
            if not quiet:
                log(f"{p:<16} {mmss(tl['duration'])}  {tl['bars']} bars  {len(tl['scenes'])} scenes  {len(tl['voice_lines'])} lines ({est} estimated)  {len(tl['captions']['cues'])} captions")
    return summary


def table(project: Path, platform: str) -> str:
    tl = load_json(Path(project) / "build" / f"timeline-{platform}.json")
    rows = [f"| # | scene | type | start | bars | narration |", "|---|---|---|---|---|---|"]
    for i, s in enumerate(tl["scenes"], 1):
        said = " ".join(v["display"] for v in tl["voice_lines"] if v["scene"] == s["id"])
        rows.append(f"| {i} | {s['id']} | {s['type']} | {mmss(s['t0'])} | {s['bars']} | {said[:90]} |")
    return "\n".join(rows)


def script_md(project: Path) -> Path:
    """A reading script: scene by scene, what is seen and what is said."""
    project = Path(project)
    cfg = project_config(project)
    sb = load_yaml(project / "storyboard.yaml")
    plat = platforms_of(cfg)[0]
    tlf = project / "build" / f"timeline-{plat}.json"
    tl = load_json(tlf) if tlf.exists() else None
    lines = [f"# {cfg['brief'].get('title', 'Script')}", "", f"Target: {cfg['brief'].get('length', '?')} s · {', '.join(platforms_of(cfg))} · {cfg['brief'].get('language')}", ""]
    if tl:
        lines.append(f"Resolved ({plat}): {mmss(tl['duration'])}, {tl['bars']} bars at {tl['bpm']:.0f} BPM")
        lines.append("")
    for s in sb["scenes"]:
        t = next((x for x in (tl or {}).get("scenes", []) if x["id"] == s["id"]), None)
        lines.append(f"## {s['id']} · {s['type']}" + (f" · {mmss(t['t0'])} ({t['bars']} bars)" if t else ""))
        p = s.get("params") or {}
        seen = [str(p[k]) for k in ("kicker", "title", "subtitle", "text", "label") if p.get(k)] + [str(x) for x in p.get("lines", []) if isinstance(x, str)] + [str(x) for x in p.get("items", []) if isinstance(x, str)]
        if seen:
            lines.append("**On screen:** " + " / ".join(seen))
        for ln in scene_lines(s, (cfg["brief"].get("voice") or {}).get("pronunciations")):
            lines.append(f"> {ln['display']}")
            if ln["say"] != ln["display"]:
                lines.append(f">  *(spoken: {ln['say']})*")
        lines.append("")
    out = project / "script.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ------------------------------------------------------------------ scaffold
def _points(brief: dict, research: dict | None) -> list[str]:
    pts = [str(p) for p in brief.get("points") or []]
    if not pts and research:
        for src in research.get("sources", []):
            for h in src.get("headings", [])[1:]:
                if 3 <= len(h.split()) <= 9 and h not in pts:
                    pts.append(h)
    return pts[:6]


# params skeleton per scene type: every string is a TODO the agent must write for THIS video
_SKEL = {
    "kinetic": {"lines": ["TODO hook line (<= 6 words)", "~TODO twist~"]},
    "title": {"kicker": "TODO", "title": "TODO", "subtitle": "TODO one-line promise"},
    "bullets": {"kicker": "TODO", "title": "TODO", "items": ["TODO", "TODO", "TODO"]},
    "steps": {"title": "TODO", "items": [{"t": "TODO", "d": "TODO"}, {"t": "TODO", "d": "TODO"}, {"t": "TODO", "d": "TODO"}]},
    "stat": {"value": 0, "label": "TODO what the number means", "source": "TODO url from brief.facts"},
    "chart": {"title": "TODO", "data": [{"label": "TODO", "value": 0}, {"label": "TODO", "value": 0}], "source": "TODO"},
    "diagram": {"title": "TODO", "nodes": [{"label": "TODO"}, {"label": "TODO"}, {"label": "TODO"}], "style": "rough"},
    "whiteboard": {"tag": "TODO", "title": "TODO", "flow": ["TODO", "TODO", "TODO"], "take": "TODO takeaway with one *accent* word"},
    "compare": {"title": "TODO", "left": {"label": "TODO", "items": ["TODO"]}, "right": {"label": "TODO", "items": ["TODO"]}},
    "terminal": {"title": "TODO", "lines": [{"cmd": "TODO"}]},
    "end": {"name": "TODO", "tagline": "TODO", "cta": "TODO"},
}


def scaffold(brief: dict, research: dict | None = None) -> dict:
    """A storyboard SKELETON from the chosen style recipe (config/styles.yaml).

    v1 wrote generic copy ("X, explained", "in 60 seconds") that leaked into
    every video. Now only the structure is generated: the beat pattern, scene
    types, transitions and notes from the style bible. Every word on screen and
    in the narration is a TODO that the agent writes fresh for this video, and
    `fishvideo gate` refuses to render while any TODO is left.
    """
    from fvcore import SKILL, load_yaml
    st = load_yaml(SKILL / "config" / "styles.yaml")
    style_id = brief.get("style") or {"story": "glow-metaphor", "promote": "studio-kinetic", "announce": "studio-kinetic"}.get(brief.get("goal"), "paper-collage")
    if (brief.get("screen") or {}).get("kind") in ("website", "desktop", "files"):
        style_id = brief.get("style") or "screen-explainer"
    style = st["styles"].get(style_id) or st["styles"]["paper-collage"]
    pts = _points(brief, research) or ["TODO point 1", "TODO point 2", "TODO point 3"]
    trans = (style.get("pacing") or {}).get("transitions") or ["cut"]
    scenes, captures = [], []
    shots = (brief.get("screen") or {}).get("shots") or []
    web = (brief.get("website") or {}).get("url") or ((brief.get("screen") or {}).get("target") if (brief.get("screen") or {}).get("kind") == "website" else "")
    k = 0
    for beat in style["beats"]:
        reps = max(1, len(pts) - 2) if beat.get("repeat") else 1
        for r in range(reps):
            typ = beat["scene"]
            sid = beat["beat"] + (str(r + 1) if reps > 1 else "")
            sc = {"id": sid, "type": typ, "note": beat.get("note", ""), "params": json.loads(json.dumps(_SKEL.get(typ, {"TODO": f"params for {typ}: see references/scene-catalogue.md"})))}
            if k:
                sc["transition"] = trans[(k - 1) % len(trans)]
            if typ == "tour":
                shot = f"shot{r + 1}"
                captures.append({"id": shot, **({"url": web, "auto": {"seconds": 8}} if web else {"source": "screenrec", "note": "TODO fishvideo screenrec record/import"})})
                sc["params"] = {"shot": shot, "frame": "inset", "eyebrow": f"STEP {r + 1}", "title": "TODO", "cam": [{"f": 0, "z": 1.0}],
                                "callouts": [{"text": "TODO", "t0": 1.0, "len": 2.0}]}
            if beat["beat"] in ("concept", "mechanism", "idea") and pts:
                sc["note"] += f" | point: {pts[min(r, len(pts) - 1)]}"
            sc["say"] = "TODO narration for this beat (write it fresh; never reuse example lines)" if brief.get("voice", {}).get("provider") != "none" else ""
            scenes.append(sc)
            k += 1
    tempo = (brief.get("tempo") or {}).get("bpm") or 120
    sb = {"title": brief.get("title") or "TODO title", "style": style_id, "bpm": tempo, "scenes": scenes, "captures": captures,
          "thumbnail": {"kicker": "TODO", "title": "TODO 2-5 big words", "accent": "TODO", "badge": "TODO"}}
    if captures:
        sb["thumbnail"]["shot"] = captures[0]["id"]
    return sb


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--scaffold", action="store_true", help="write storyboard.yaml from the brief if it does not exist")
    ap.add_argument("--force", action="store_true", help="with --scaffold: overwrite an existing storyboard")
    ap.add_argument("--script", action="store_true", help="also write script.md")
    ap.add_argument("--table", default=None, help="print the scene table for a platform")
    a = ap.parse_args(argv)
    project = ensure_project(a.project)
    if a.scaffold:
        f = project / "storyboard.yaml"
        if f.exists() and not a.force:
            log(f"{f} exists; keeping it (use --force to replace)")
        else:
            rs = project / "research" / "sources.json"
            save_yaml(f, scaffold(project_config(project)["brief"], load_json(rs) if rs.exists() else None))
            log(f"scaffolded {f}")
    build(project)
    if a.script:
        log(f"wrote {script_md(project)}")
    if a.table:
        log(table(project, a.table))
    return 0


if __name__ == "__main__":
    main_guard(cli)
