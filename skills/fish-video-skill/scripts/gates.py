"""Quality gates a weaker model cannot skip: measured, not judged.

    fishvideo gates <dir> [--platform p] [--recipe r]   imagery coverage of the storyboard against the recipe's thresholds
    fishvideo signoff <dir> [--platform p]              write the frame-sheet checklist (build/<p>/review/SIGNOFF.md) to fill in
    fishvideo signoff <dir> --check                     verify the checklist is complete and newer than the last render

Imagery gate. Every scene is classified from the storyboard (never from its text):
  image    a real raster picture or footage is on screen (a jpg/png/webp/mp4 path anywhere in its params, or a footage/meme/tour scene)
  graphic  drawn visuals with no photograph (diagram, collage shapes, roadmap map, flow ...)
  text     words on a card (title, kinetic, quote, bullets, stat, statement, cards, end ...)
Measured over the timeline (or bars / dur / spoken words when no timeline exists yet):
  image_share        share of running time with an image scene on screen
  image_changes_pm   distinct images brought on screen per minute (a photo that swaps inside a scene counts each time)
  longest_no_image   longest stretch in seconds without an image
  text_share         share of running time on text cards
Thresholds live in config/recipes.yaml per recipe (tuned on the benchmark videos; see references/recipes.md).
A video with `recipe:` in its brief fails `fishvideo gate` (and so render) when a threshold is missed; without a recipe the
generic thresholds only warn. Sign-off: the frame sheet must be opened and every beat described and judged.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from fvcore import FishError, load_json, load_yaml, log, main_guard, project_config, SKILL

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".mp4", ".webm", ".mov")
IMAGE_TYPES = {"footage", "meme", "tour", "image"}
GRAPHIC_TYPES = {"collage", "diagram", "whiteboard", "neonline", "split", "chart", "glowshape", "tunnel", "ringbloom", "orbit", "cone", "coinflip", "compare", "flow", "roadmap", "terminal", "bold"}
TEXT_TYPES = {"title", "kinetic", "quote", "bullets", "stat", "end", "steps", "stepcard", "statement", "cards", "thumbnail"}
SCREENSHOT_TYPES = {"site", "tour", "pile"}
SCREENSHOT_HINTS = ("screenshot", "capture", "shots/", "shot-", "browser")
LABEL_TYPES = {"story", "image", "statement"}            # photos of people and events: a generic picture could be mistaken for the real one
LABELS = ("archive photo", "illustrative")
OWN_DIRS = ("assets/shots/", "assets/own/")
GENERIC = {"sharp_share_min": 0, "image_share_min": 0.35, "image_changes_pm_min": 4, "longest_no_image_max": 45, "text_share_max": 0.5, "image_beats_min": 0.3, "screenshot_of_images_max": 0.8, "photo_share_min": 0.10}


def _paths(obj, out: list) -> None:
    if isinstance(obj, str):
        if obj.lower().split("?")[0].endswith(IMG_EXT):
            out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("_"):                          # internal params the build adds (_px sizes, _ground copies) are not pictures a beat shows
                continue
            if k in ("clip",) and isinstance(v, str):
                out.append("clip:" + v)
            else:
                _paths(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _paths(v, out)


def classify(scene: dict) -> tuple[str, list[str]]:
    """(kind, distinct image sources) for one scene."""
    params = scene.get("params") or {}
    srcs: list[str] = []
    _paths(params, srcs)
    srcs = list(dict.fromkeys(srcs))
    t = scene.get("type")
    if t in IMAGE_TYPES and not srcs:
        srcs = [f"{t}:{scene.get('id')}"]
    if srcs:
        return "image", srcs
    if t in TEXT_TYPES:
        return "text", []
    return "graphic", []


def scene_times(project: Path, platform: str | None) -> tuple[list[dict], str]:
    """[{id, type, params, t0, t1}] from the built timeline, else from the storyboard (bars, dur or spoken words)."""
    bt = project / "build"
    tls = sorted(bt.glob("timeline-*.json")) if bt.exists() else []
    tls = [f for f in tls if "thumbnail" not in f.name]
    if platform:
        tls = [f for f in tls if f.name == f"timeline-{platform}.json"] or tls
    if tls:
        tl = load_json(tls[0])
        return [{"id": s["id"], "type": s["type"], "params": s.get("params") or {}, "t0": s["t0"], "t1": s["t1"]} for s in tl["scenes"]], tls[0].stem.replace("timeline-", "")
    sb = load_yaml(project / "storyboard.yaml")
    bpm = float(sb.get("bpm") or 120)
    bar = 4 * 60 / bpm
    out, t = [], 0.0
    for s in sb["scenes"]:
        say = s.get("say") or ""
        words = len(" ".join(say if isinstance(say, list) else [say]).split())
        d = float(s["dur"]) if s.get("dur") else float(s["bars"]) * bar if s.get("bars") else max(float(s.get("bars_min") or 0) * bar, words / 2.8, 2.0)
        out.append({"id": s["id"], "type": s["type"], "params": s.get("params") or {}, "t0": t, "t1": t + d})
        t += d
    return out, "storyboard"


def measure(project: Path, platform: str | None = None) -> dict:
    scenes, src = scene_times(Path(project), platform)
    total = scenes[-1]["t1"] - scenes[0]["t0"] if scenes else 0.0
    if total <= 0:
        raise FishError("the storyboard has no running time to measure")
    share = {"image": 0.0, "graphic": 0.0, "text": 0.0}
    changes, gap, longest, last_img_end = 0, 0.0, 0.0, 0.0
    rows = []
    t_prev = scenes[0]["t0"]
    for s in scenes:
        kind, srcs = classify(s)
        d = s["t1"] - s["t0"]
        share[kind] += d
        if kind == "image":
            longest = max(longest, s["t0"] - last_img_end)
            last_img_end = s["t1"]
            changes += len(srcs)
        shot = kind == "image" and (s["type"] in SCREENSHOT_TYPES or all(any(h in x.lower() for h in SCREENSHOT_HINTS) for x in srcs))
        rows.append({"id": s["id"], "type": s["type"], "kind": kind, "seconds": round(d, 2), "images": len(srcs), "srcs": srcs, "screenshot": shot})
    longest = max(longest, scenes[-1]["t1"] - last_img_end)
    shot_sec = sum(r["seconds"] for r in rows if r["kind"] == "image" and r["screenshot"])
    beats = sum(1 for r in rows if r["kind"] == "image")
    return {"source": src, "seconds": round(total, 1), "scenes": len(scenes), "image_share": round(share["image"] / total, 3),
            "image_beats": round(beats / len(scenes), 3), "screenshot_share": round(shot_sec / total, 3),
            "screenshot_of_images": round(shot_sec / share["image"], 3) if share["image"] else 0.0, "photo_share": round((share["image"] - shot_sec) / total, 3),
            "graphic_share": round(share["graphic"] / total, 3), "text_share": round(share["text"] / total, 3),
            "image_changes_pm": round(changes / (total / 60), 1), "longest_no_image": round(longest, 1), "rows": rows}


def recipe_gate(name: str | None) -> dict:
    if not name:
        return dict(GENERIC)
    import recipes
    return {**GENERIC, **(recipes.get(name).get("gate") or {})}


def abstract_optout(brief: dict) -> tuple[bool, str | None]:
    """(opted_out, problem). Only an explicit, user-requested abstract or text-led video may skip the imagery rules."""
    v = brief.get("visuals") or {}
    if v.get("mode") not in ("abstract", "text-led"):
        return False, None
    if v.get("user_asked") is True and str(v.get("reason") or "").strip():
        return True, None
    return False, "visuals.mode is abstract but `user_asked: true` and a `reason:` (the user's words) are missing: the opt-out is only for a user who asked for an abstract or text-led video"


def credit_index(project: Path) -> dict:
    f = Path(project) / "assets" / "credits.json"
    out = {}
    if f.exists():
        for c in load_json(f):
            if isinstance(c, dict) and c.get("file"):
                out[c["file"].replace("\\", "/")] = c
    return out


def provenance(project: Path, rows: list[dict]) -> list[str]:
    """Real images must exist and carry a recorded source, licence and author (assets/credits.json). Own captures (assets/shots, assets/own) are exempt from the author rule."""
    project = Path(project)
    idx = credit_index(project)
    out = []
    for r in rows:
        if r["kind"] != "image":
            continue
        for x in r["srcs"]:
            if ":" in x and not x.startswith("assets/"):
                continue                                                  # footage clip ids are recorded by `assets clip`
            if not (project / x).exists():
                out.append(f"beat {r['id']}: {x} does not exist. Fetch it: fishvideo assets source <dir> \"<what it shows>\" --beat {r['id']}")
                continue
            if x.startswith(OWN_DIRS) and not x.startswith("assets/own/"):
                continue
            c = idx.get(x)
            if not c:
                out.append(f"beat {r['id']}: {x} has no credit record (source, licence, author). Fetch it with `fishvideo assets source <dir> \"<query>\" --beat {r['id']}` or record it in assets/credits.json")
            else:
                miss = [k for k in ("url", "license", "author") if not str(c.get(k) or "").strip()]
                if miss:
                    out.append(f"beat {r['id']}: {x} credit record lacks {', '.join(miss)}")
    return out


MAX_UPSCALE = 2.2               # a picture is never enlarged past this; below the minimum frame share it is too small for its use
MIN_FRAME_SHARE = 0.88          # the picture must cover at least this share of the frame width at MAX_UPSCALE


def story_fit(nw: int, nh: int, W: int, H: int) -> dict:
    """Mirror of L.storyFit in scenes/story.js: full-bleed when sharp enough (cover scale <= 1.3), else a framed card (88% of the frame width) never enlarged past 2.2x."""
    cover = max(W / nw, H / nh)
    return {"mode": "bleed", "scale": cover} if cover <= 1.3 else {"mode": "frame", "scale": min(MAX_UPSCALE, cover)}


PANEL_HEIGHT_SHARE = 0.5        # the default panel is about half the frame tall (50-58%)


def min_native_width(W: int) -> int:
    return int(MIN_FRAME_SHARE * W / MAX_UPSCALE)


def min_native_height(H: int) -> int:
    return int(PANEL_HEIGHT_SHARE * H / MAX_UPSCALE)


def frame_size(project: Path, platform: str | None) -> tuple[int, int]:
    project = Path(project)
    tls = [f for f in sorted((project / "build").glob("timeline-*.json")) if "thumbnail" not in f.name] if (project / "build").exists() else []
    if platform:
        tls = [f for f in tls if f.name == f"timeline-{platform}.json"] or tls
    if tls:
        tl = load_json(tls[0])
        return int(tl["W"]), int(tl["H"])
    cfg = project_config(project)
    import storyboard as sbm
    prof = cfg["platforms"][sbm.platforms_of(cfg)[0]]
    return int(prof["W"]), int(prof["H"])


def resolution(project: Path, rows: list[dict], platform: str | None = None) -> list[str]:
    """Rendered-scale check: a picture whose native size cannot cover MIN_FRAME_SHARE of the frame at MAX_UPSCALE is too small for its use."""
    project = Path(project)
    W, H = frame_size(project, platform)
    need = min_native_width(W)
    out = []
    try:
        from PIL import Image
    except ImportError:
        return out
    for r in rows:
        if r["kind"] != "image" or r["screenshot"] or r["type"] not in LABEL_TYPES:
            continue
        for x in r["srcs"]:
            f = project / x
            if not f.exists() or not x.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            try:
                with Image.open(f) as im:
                    nw, nh = im.size
            except Exception:                                                         # noqa: BLE001
                out.append(f"beat {r['id']}: {x} cannot be read as a picture (corrupt or not an image). Fetch it again: fishvideo assets source <dir> \"<query>\" --beat {r['id']}")
                continue
            need_h = min_native_height(H)
            if nw < need or nh < need_h:
                out.append(f"beat {r['id']}: {x} is {nw}x{nh}, too small for its panel in a {W}x{H} frame (an 88% x {PANEL_HEIGHT_SHARE:.0%} panel would enlarge it "
                           f"{max(W * MIN_FRAME_SHARE / nw, H * PANEL_HEIGHT_SHARE / nh):.1f}x; the limit is {MAX_UPSCALE}x, which needs {need}x{need_h} px or more). "
                           f"Fetch a larger one: fishvideo assets source <dir> \"<query>\" --beat {r['id']} --min-width {need} --min-height {need_h}")
    return out


def duplicate_srcs(project: Path, rows: list[dict]) -> list[str]:
    """A beat must never list the same picture twice (same path, or two files with the same picture): a second panel needs a DIFFERENT picture."""
    from PIL import Image
    import numpy as np
    project = Path(project)
    out = []
    for r in rows:
        if r["kind"] != "image" or r["type"] not in LABEL_TYPES or len(r["srcs"]) < 2:
            continue
        paths = [x for x in r["srcs"] if x.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
        if len(set(paths)) < len(paths):
            out.append(f"beat {r['id']}: the same picture is listed twice. A second panel needs a different picture file: fishvideo assets source <dir> \"<query>\" --beat {r['id']}")
            continue
        hs = []
        for x in paths:
            f = project / x
            if f.exists():
                try:
                    with Image.open(f) as im:
                        a = np.asarray(im.convert("L").resize((16, 16)), dtype=np.float32)
                    hs.append((x, a > a.mean()))
                except Exception:                                                            # noqa: BLE001
                    pass
        for i in range(len(hs)):
            for j in range(i + 1, len(hs)):
                if int((hs[i][1] != hs[j][1]).sum()) <= 12:
                    out.append(f"beat {r['id']}: {hs[i][0]} and {hs[j][0]} are the same picture. A second panel needs a different picture: fishvideo assets source <dir> \"<query>\" --beat {r['id']}")
    return out


def labels(project: Path, scenes_params: dict, rows: list[dict]) -> list[str]:
    """Honesty guard: a photo of a person or event needs an `archive photo` or `illustrative` label unless its credit says it truly depicts the subject."""
    idx = credit_index(project)
    out = []
    for r in rows:
        if r["kind"] != "image" or r["type"] not in LABEL_TYPES or r["screenshot"]:
            continue
        p = scenes_params.get(r["id"]) or {}
        lab = str(p.get("label") or "").strip().lower()
        verified = all((idx.get(x) or {}).get("depicts_verified") for x in r["srcs"])
        if lab not in LABELS and not verified:
            out.append(f"beat {r['id']}: add `label: archive photo` (a real photo of this person or event) or `label: illustrative` (a generic picture), shown on screen so nobody mistakes it for the real thing")
    return out


def check(project: Path, platform: str | None = None, recipe: str | None = None, provenance_checks: bool = True) -> tuple[dict, list[str]]:
    """(metrics, failures). A failure line says what to change. Coverage is measured; provenance and labels are checked per beat."""
    project = Path(project)
    brief = project_config(project)["brief"]
    name = recipe or brief.get("recipe")
    m = measure(project, platform)
    g = recipe_gate(name)
    f = []
    opted, problem = abstract_optout(brief)
    if problem:
        f.append(problem)
    m["recipe"] = name or "generic"
    m["thresholds"] = g
    m["opt_out"] = opted
    if opted:
        return m, f
    if m["image_share"] < g["image_share_min"]:
        f.append(f"real images or footage are on screen {m['image_share']:.0%} of the time; this recipe needs {g['image_share_min']:.0%}+. Beats with no image: {', '.join(r['id'] for r in m['rows'] if r['kind'] != 'image')[:200]}. Fetch real ones: fishvideo assets source <dir> \"<query>\" --beat <id>")
    if m["image_beats"] < g["image_beats_min"]:
        f.append(f"only {m['image_beats']:.0%} of the beats have a real image or footage; the asset plan must give most beats one (needs {g['image_beats_min']:.0%}+)")
    if m["image_changes_pm"] < g["image_changes_pm_min"]:
        f.append(f"a new image arrives {m['image_changes_pm']}/min; needs {g['image_changes_pm_min']}+. Use `srcs:` to swap photos inside a scene, or split long scenes")
    if m["longest_no_image"] > g["longest_no_image_max"]:
        f.append(f"{m['longest_no_image']} s pass with no image; the limit is {g['longest_no_image_max']} s. Add a photo or footage scene in that stretch")
    if m["text_share"] > g["text_share_max"]:
        f.append(f"{m['text_share']:.0%} of the time is text cards; the limit is {g['text_share_max']:.0%}. Replace text cards with `story` scenes or add imagery")
    if m["photo_share"] < g["photo_share_min"]:
        f.append(f"real photos, footage or product visuals (not site screenshots) fill {m['photo_share']:.0%} of the time; needs {g['photo_share_min']:.0%}+. Fetch some: fishvideo assets source <dir> \"<query>\" --beat <id>")
    if m["image_share"] and m["screenshot_of_images"] > g["screenshot_of_images_max"]:
        f.append(f"website screenshots are {m['screenshot_of_images']:.0%} of the image time; a site screenshot cannot be the main visual (limit {g['screenshot_of_images_max']:.0%}). Add photos, footage or product visuals")
    if "graphic_share_min" in g and m["graphic_share"] + m["image_share"] < g["graphic_share_min"]:
        f.append(f"only {(m['graphic_share'] + m['image_share']):.0%} of the time shows drawn or photographic visuals; needs {g['graphic_share_min']:.0%}+")
    if provenance_checks:
        sbf = project / "storyboard.yaml"
        params = {s["id"]: s.get("params") or {} for s in (load_yaml(sbf).get("scenes") or [])} if sbf.exists() else {}
        pv, rs, lb = provenance(project, m["rows"]), resolution(project, m["rows"], platform), labels(project, params, m["rows"])
        f += pv + rs + lb + duplicate_srcs(project, m["rows"])
        if pv or lb:
            f.append(f"EXISTING PROJECT? {len(pv)} image(s) lack a credit record and {len(lb)} beat(s) lack a label: nothing was changed. If the pictures really come from where you say, record them in one command: "
                     f"`fishvideo assets adopt {project.name} --license \"<licence>\" --author \"<author>\" --source <url> --label illustrative` (you are asserting those facts; per-file records via `assets source` are better)")
    return m, f


# ------------------------------------------------------------------ sharp image coverage, measured on the rendered frames
SHARP_BLOCK, SHARP_T = 24, 6.0          # 24 px blocks of a 540-wide frame; mean gradient above 6 = real picture detail (a blurred backdrop is near 0)


def _sharp_mask(png: Path):
    import numpy as np
    from PIL import Image
    im = Image.open(png).convert("L")
    g = np.asarray(im, dtype=np.float32)
    e = np.abs(np.diff(g, axis=1))[:-1, :] + np.abs(np.diff(g, axis=0))[:, :-1]
    B = SHARP_BLOCK
    hh, ww = e.shape[0] // B, e.shape[1] // B
    return g, (e[:hh * B, :ww * B].reshape(hh, B, ww, B).mean(axis=(1, 3)) > SHARP_T)


def _components(mask, min_blocks: int = 40) -> list[list[tuple[int, int]]]:
    seen = mask.copy() * False
    out = []
    for y in range(mask.shape[0]):
        for x in range(mask.shape[1]):
            if mask[y, x] and not seen[y, x]:
                stack, cells = [(y, x)], []
                seen[y, x] = True
                while stack:
                    cy, cx = stack.pop()
                    cells.append((cy, cx))
                    for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                        if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
                if len(cells) >= min_blocks:
                    out.append(cells)
    return out


DUP_SIMILARITY = 0.65           # tuned: stacked duplicate panels measured 0.53-0.89 (mostly 0.66+), the Onoda v2 frames never above 0.61


def panel_analysis(png: Path, sim: float = DUP_SIMILARITY) -> dict:
    """The sharp picture of one frame: {share (unique area), raw (all sharp area), duplicates: [(split, similarity)]}.
    The frame's sharp area is cut in two at every plausible row (stacked panels, the words between them); when the two
    halves, downscaled to grey 32x32, correlate above `sim`, the same picture is on screen twice (whatever the crop or pan) and the
    repeat's area is not counted."""
    import numpy as np
    from PIL import Image
    g, mask = _sharp_mask(png)
    B = SHARP_BLOCK
    raw = float(mask.mean())
    if not mask.any():
        return {"share": 0.0, "raw": 0.0, "duplicates": [], "panels": 0}
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1

    def vec(a, b, c, d):
        if b - a < 3 or d - c < 3:
            return None
        v = np.asarray(Image.fromarray(g[a * B:b * B, c * B:d * B].astype("uint8")).resize((32, 32)), dtype=np.float32).ravel()
        return (v - v.mean()) / (v.std() + 1e-6)
    best = (0.0, None)
    if y1 - y0 >= 12:                                                         # stacked: split rows
        for r in range(y0 + (y1 - y0) // 3, y0 + 2 * (y1 - y0) // 3 + 1):
            for gap in (0, 2, 4):
                top, bot = vec(y0, r - gap // 2, x0, x1), vec(r + gap - gap // 2, y1, x0, x1)
                if top is not None and bot is not None:
                    c = float(np.dot(top, bot) / len(top))
                    if c > best[0]:
                        best = (c, ("rows", r))
    dups = [(best[1], round(best[0], 2))] if best[0] >= sim else []
    share = raw
    if dups:
        kind, at = dups[0][0]
        rep = mask.copy() * False
        rep[at:y1, x0:x1] = mask[at:y1, x0:x1]
        share = float((mask & ~rep).mean())
    return {"share": share, "raw": raw, "duplicates": dups, "panels": 2 if dups else 1}


def sharp_share_of(png: Path) -> float:
    """Share of the frame covered by UNIQUE sharp picture detail: not the blurred backdrop, not flat colour, and a panel that repeats another panel counts once."""
    return panel_analysis(png)["share"]


def sharp_coverage(video: Path, scenes: list[dict], work: Path | None = None) -> dict:
    """Frames at 80% of every scene (540 px wide) -> per-scene and time-weighted mean share of sharp picture. Works on any rendered video."""
    import shutil
    import subprocess
    import tempfile
    from fvcore import ffmpeg_bin
    out = []
    td = Path(tempfile.mkdtemp(prefix="fvsharp-"))
    try:
        for i, s in enumerate(scenes):
            t = s["t0"] + (s["t1"] - s["t0"]) * 0.8
            f = td / f"{i:03d}.png"
            subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=540:-2", str(f)], check=False)
            if f.exists():
                a = panel_analysis(f)
                out.append({"id": s["id"], "seconds": s["t1"] - s["t0"], "share": round(a["share"], 3), "duplicates": len(a["duplicates"])})
    finally:
        shutil.rmtree(td, ignore_errors=True)
    tot = sum(r["seconds"] for r in out) or 1
    return {"mean": round(sum(r["share"] * r["seconds"] for r in out) / tot, 3), "min": round(min((r["share"] for r in out), default=0), 3), "duplicates": [r["id"] for r in out if r["duplicates"]], "scenes": out}


def sharp_failures(project: Path, video: Path, recipe: str | None = None) -> tuple[dict, list[str]]:
    g = recipe_gate(recipe or project_config(project)["brief"].get("recipe"))
    need = g.get("sharp_share_min", 0)
    scenes, _ = scene_times(project, None)
    m = sharp_coverage(video, scenes)
    f = []
    if m["duplicates"]:
        f.append(f"near-identical panels on screen at once in {', '.join(m['duplicates'][:6])}: the same picture is shown twice. Use ONE panel per beat, or give the beat a second DIFFERENT picture file (assets source <dir> \"<query>\" --beat <id>)")
    if need and m["mean"] < need:
        weak = ", ".join(f"{r['id']} {r['share']:.0%}" for r in sorted(m["scenes"], key=lambda r: r["share"])[:4])
        f.append(f"sharp picture covers {m['mean']:.0%} of the frame on average; this recipe needs {need:.0%}+ (weakest: {weak}). Make the pictures fill the frame: a bigger or second image, "
                 "or a full-bleed photo, instead of a small card on a blurred backdrop")
    return m, f


# ------------------------------------------------------------------ word budget per slot (before any voice is generated)
WPS = 2.3                      # words per second the chatterbox-soft preset really delivers once pauses are counted


def _spoken_words(say) -> int:
    text = " ".join(say) if isinstance(say, list) else str(say or "")
    text = re.sub(r"\{[^|}]*\|([^}]*)\}", r"\1", text)
    return len(re.findall(r"[\w'-]+", text))


def budget(project: Path) -> list[dict]:
    """Per beat: the slot (bars or dur), the most words that fit, the words written, and whether it fits."""
    project = Path(project)
    sb = load_yaml(project / "storyboard.yaml")
    bar = 4 * 60 / float(sb.get("bpm") or 120)
    rows = []
    for s_ in sb.get("scenes", []):
        secs = float(s_["dur"]) if s_.get("dur") else float(s_["bars"]) * bar if s_.get("bars") else float(s_["bars_min"]) * bar if s_.get("bars_min") else None
        if secs is None:
            continue
        say = s_.get("say")
        words = _spoken_words(say)
        mx = max(3, int((secs - 0.6) * WPS))
        rows.append({"beat": s_["id"], "seconds": secs, "max_words": mx, "words": words, "fixed": bool(s_.get("bars") or s_.get("dur")), "over": words > mx and "TODO" not in str(say)})
    return rows


def budget_errors(project: Path) -> list[str]:
    return [f"beat {r['beat']}: {r['words']} words do not fit its {r['seconds']:.0f} s slot (max {r['max_words']}). Shorten the line, give the beat more bars, or replace `bars:` with `bars_min:` so the narration sets the length. Do it BEFORE generating the voice (a voice run is minutes)" for r in budget(project) if r["over"] and r["fixed"]]            # a flexible (bars_min) beat just stretches


def budget_cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fishvideo budget")
    ap.add_argument("project")
    a = ap.parse_args(argv)
    bad = 0
    for r in budget(Path(a.project)):
        log(f"{r['beat']:<20} {r['seconds']:>4.0f} s  max {r['max_words']:>2} words  written {r['words']:>2}  {'OVER' if r['over'] else 'ok'}")
        bad += r["over"]
    return 1 if bad else 0


# ------------------------------------------------------------------ frame-sheet sign-off
def _review_dir(project: Path, platform: str) -> Path:
    return project / "build" / platform / "review"


def signoff_template(project: Path, platform: str | None = None) -> Path:
    project = Path(project)
    scenes, src = scene_times(project, platform)
    plat = platform or (src if src != "storyboard" else "youtube")
    d = _review_dir(project, plat)
    d.mkdir(parents=True, exist_ok=True)
    lines = ["# Frame-sheet sign-off", "",
             f"Platform `{plat}`. Open the sheet(s) in `build/{plat}/review/` (run `fishvideo review {project.name} --platform {plat}` first) and the contact sheet.",
             "Fill every row. `see` = one sentence naming every object on screen (an object that needs explaining is a problem). `verdict` = ok or fix. Do not ship while any row says fix.", "",
             "Checklist (answer each with yes or the fix you made):",
             "- [ ] Every frame has a picture, footage or drawn graphic, not only words",
             "- [ ] Nothing is empty: no bare colour or blank half-frame",
             "- [ ] Hero word is 3x the small text; text is inside the safe area and not under the platform UI",
             "- [ ] Captions are legible on the busiest frame",
             "- [ ] No website screenshot is used as thumbnail or cover",
             "- [ ] No face or head is cut off by a card, a crop view or a tile (there is no face detector: look at every framed picture, both crop views, and every thumbnail tile)",
             "- [ ] Logos or photos shown relate to what the narration says at that moment", "",
             "| scene | t | kind | see | verdict |", "|---|---|---|---|---|"]
    for s in scenes:
        kind, _ = classify(s)
        lines.append(f"| {s['id']} | {s['t0']:.1f} | {kind} | TODO | TODO |")
    f = d / "SIGNOFF.md"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


def signoff_errors(project: Path, platform: str | None = None) -> list[str]:
    project = Path(project)
    plats = [platform] if platform else [p.parent.parent.name for p in (project / "build").glob("*/review/SIGNOFF.md")]
    if not plats:
        return ["no frame-sheet sign-off: run `fishvideo signoff <dir>`, open the frame sheet and fill build/<platform>/review/SIGNOFF.md"]
    errs = []
    for plat in plats:
        f = _review_dir(project, plat) / "SIGNOFF.md"
        if not f.exists():
            errs.append(f"{plat}: no SIGNOFF.md: run `fishvideo signoff {project.name} --platform {plat}`")
            continue
        text = f.read_text(encoding="utf-8")
        if re.search(r"- \[ \]", text):
            errs.append(f"{plat}: SIGNOFF.md still has unchecked checklist items")
        for row in [r for r in text.splitlines() if r.startswith("|") and not r.startswith("|---") and not r.startswith("| scene")]:
            cells = [c.strip() for c in row.strip("|").split("|")]
            if len(cells) < 5:
                continue
            see, verdict = cells[3], cells[4].lower()
            if "todo" in see.lower() or len(see.split()) < 4:
                errs.append(f"{plat}: scene {cells[0]}: describe what you see (4+ words, name each object)")
            if verdict != "ok":
                errs.append(f"{plat}: scene {cells[0]}: verdict is '{cells[4]}', not ok")
        finals = list((project / "build" / plat).glob("final*.mp4"))
        if finals and f.stat().st_mtime < max(x.stat().st_mtime for x in finals) - 1:
            errs.append(f"{plat}: SIGNOFF.md is older than the last render: look at the new frames and sign again")
    return errs[:12]


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fishvideo gates", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project"); ap.add_argument("--platform", default=None); ap.add_argument("--recipe", default=None)
    ap.add_argument("--json", action="store_true"); ap.add_argument("--coverage-only", action="store_true", help="skip the per-file provenance and label checks")
    a = ap.parse_args(argv)
    m, f = check(Path(a.project), a.platform, a.recipe, not a.coverage_only)
    if a.json:
        print(json.dumps({k: v for k, v in m.items() if k != "rows"}, indent=1))
    else:
        log(f"imagery ({m['recipe']}, {m['seconds']} s from {m['source']}): images {m['image_share']:.0%}, drawn {m['graphic_share']:.0%}, text {m['text_share']:.0%}; "
            f"{m['image_changes_pm']} new images/min; longest stretch without one {m['longest_no_image']} s")
        for x in f:
            log("FAIL " + x)
        if not f:
            log("PASS imagery gate")
    return 1 if f else 0


def signoff_cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fishvideo signoff")
    ap.add_argument("project"); ap.add_argument("--platform", default=None); ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        e = signoff_errors(Path(a.project), a.platform)
        for x in e:
            log("FAIL " + x)
        if not e:
            log("PASS sign-off complete")
        return 1 if e else 0
    f = signoff_template(Path(a.project), a.platform)
    log(f"checklist written: {f}\nOpen the review sheets, fill every row (see + verdict) and tick the boxes. Then: fishvideo signoff {a.project} --check")
    return 0


if __name__ == "__main__":
    main_guard(cli)
