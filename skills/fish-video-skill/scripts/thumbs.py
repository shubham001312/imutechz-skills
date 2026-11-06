"""Thumbnail tools: design, check, preview, choose and ship the picture people click on.

    fishvideo thumb make <dir> [--variants N]          distinct layouts at 1280x720 (+ vertical covers for 9:16 projects)
    fishvideo thumb check <dir> [--file f] [--all]     legibility at the sizes a feed really shows, and the hard limits
    fishvideo thumb sheet <dir>                        a mock feed, light and dark, with the variants among grey placeholders
    fishvideo thumb pick <dir> <n> [--cover m]         record the chosen variant: `package` ships it
    fishvideo thumb cutout <image> [--out f] [--outline 10] [--glow 34]   a subject with outline and glow, ready for a layout
    fishvideo thumbnail <dir> [--no-covers]            THE REQUIRED STEP: the house `road` thumbnail (+ 9:16 covers), checked, picked: `package` refuses without it
    fishvideo thumb logos [<dir>] [--find text] [--slugs a,b]   brand logos (simple-icons) for the tiles: search, resolve, relevance check

Layouts (scripts/stage/scenes/thumbs.js, drawn by the stage like every other frame):
subject (big words + a cut-out), number (one giant figure), split (before / after), caption (a frame
with the words low and left), frame (the best frame in a card) and road (the house design: a two-tone headline and
logo or picture tiles along a glowing road; `thumbnail: {logos: [slug, ...]}` or licensed pictures). A website screenshot is never used as a thumbnail or cover:
scenes that show one are skipped when frames are picked, and `thumb check` FAILs a picture that looks like one. Frames come from the video itself:
the scenes are rendered, scored (detail, colour, contrast, emptiness) and the best are used.

Everything lands in <dir>/build/thumbnail/: variants/thumb-<n>-<layout>.png (+ .json: the text the
stage drew, which `thumb check` measures), covers/, variants.json, pick.json, sheet and feed images.
`thumb check` FAILs only on facts (size over 2 MB, wrong shape); everything about looks is a WARN.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
from pathlib import Path

import design as dz
from fvcore import SKILL, FishError, ensure_project, last_json_line, load_json, load_yaml, log, main_guard, node, project_config, save_json, save_yaml, warn

MAX_BYTES = 2_000_000
SIZES = {"tiny": (246, 138), "feed": (320, 180), "side": (168, 94)}     # the sizes a thumbnail is really shown at
LIMITS = {
    "font_tiny": 12,        # ... and at 246x138, where a feed shows a thumbnail small
    "font_feed": 16,        # the title's font size, in px, at 320x180 (that is 26 px on the 1280 original)
    "font_side": 9,         # ... and at 168x94
    "font_floor": 6,        # below this at 168 wide nobody can read it: FAIL-level unreadable
    "contrast": 3.0,        # WCAG ratio of the title against what is behind it, measured on the downscaled picture
    "contrast_floor": 1.5,
    "words_ok": 6, "words_max": 9,
    "bright": (0.14, 0.82), "range": 0.45, "sat": 0.12, "vivid": 0.01,
    "tile_upscale": 1.5,    # a tile picture is never enlarged past this (shorter side of the original)
    "tile_margin": 16,      # px at 1280 wide: tiles stay this far from the frame edge
    "tile_gap": 12,         # px at 1280 wide: the least space between a word box and a tile
    "stamp": (0.84, 0.86),   # the bottom-right corner a feed covers with the duration: x and y start, as shares of the frame
    "stamp_edges": 0.06,     # the share of edge pixels allowed in it
}
LAYOUTS = ["road", "subject", "caption", "number", "split", "frame"]
VERTICAL_LAYOUTS = ["road", "subject", "caption"]
SKIP_TYPES = {"end", "thumbnail", "title"}
SCREENSHOT_TYPES = {"site", "tour", "pile", "capture", "browser"}     # scenes that show a website: never a thumbnail or cover
SCREENSHOT_HINTS = ("screenshot", "capture", "shot-", "/shots/", "browser")


def tdir(project: Path) -> Path:
    d = Path(project) / "build" / "thumbnail"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------------ pictures from the film
def frame_score(img) -> float:
    """How good a frame looks as a thumbnail background: detail, colour and tonal range, minus empty quarters."""
    import numpy as np
    a = img[::3, ::3].astype(np.float32)
    g = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    edge = float(np.abs(np.diff(g, axis=1)).mean() + np.abs(np.diff(g, axis=0)).mean())
    colour = float(np.std(a[..., 0] - a[..., 1]) + np.std(0.5 * (a[..., 0] + a[..., 1]) - a[..., 2]))
    rng = float(np.percentile(g, 97) - np.percentile(g, 3))
    return edge * 2.0 + colour * 0.5 + rng * 0.3 - 20 * len(dz.empty_quadrants(img))


def is_screenshot_path(path: str) -> bool:
    low = path.lower().replace("\\", "/")
    return any(h in low for h in SCREENSHOT_HINTS)


def looks_like_screenshot(rgb) -> bool:
    """True when the picture holds a browser title bar: the red, yellow and green window dots in a row."""
    import numpy as np
    a = rgb.astype(np.int16)
    H = a.shape[0]
    top = a[: int(H * 0.5)]
    def blobs(col):
        m = (np.abs(top - np.array(col)).max(axis=2) < 26)
        ys, xs = np.nonzero(m)
        return list(zip(ys.tolist(), xs.tolist()))[:20000]
    pts = [blobs(c) for c in ((255, 95, 87), (254, 188, 46), (40, 200, 64))]
    if not all(len(p) >= 12 for p in pts):
        return False
    c = [(float(np.mean([y for y, _ in p])), float(np.mean([x for _, x in p]))) for p in pts]
    return abs(c[0][0] - c[1][0]) < 6 and abs(c[1][0] - c[2][0]) < 6 and c[0][1] < c[1][1] < c[2][1] and (c[2][1] - c[0][1]) < rgb.shape[1] * 0.1


def best_frames(project: Path, platform: str, keep: int = 3) -> list[dict]:
    """Render every scene of a platform and rank the frames. Returns [{file, scene, type, score, t}], best first,
    copied to build/thumbnail/src/ as JPEG."""
    from PIL import Image
    tl = dz.ensure_timeline(project, platform)
    r = node("stills.mjs", project, "--platform", platform, "--scenes", capture=True, check=False)
    res = last_json_line(r.stdout or "") or {}
    files = res.get("stills") or []
    scenes = tl["scenes"]
    if r.returncode != 0 or len(files) != len(scenes):
        raise FishError(f"could not render the scenes of {platform}: {((r.stderr or '') + (r.stdout or ''))[-300:]}")
    rows = []
    for sc, f in zip(scenes, files):
        if sc["type"] in SKIP_TYPES and len(scenes) > 3:
            continue
        if sc["type"] in SCREENSHOT_TYPES or is_screenshot_path(str((sc.get("params") or {}).get("src") or "")):
            continue
        rows.append({"scene": sc["id"], "type": sc["type"], "t": round(sc["t0"] + (sc["t1"] - sc["t0"]) * 0.8, 2), "file": f, "score": round(frame_score(dz.load_rgb(f)), 1)})
    rows.sort(key=lambda x: -x["score"])
    out = tdir(project) / "src"
    out.mkdir(exist_ok=True)
    for old in out.glob("frame-*.jpg"):
        old.unlink()
    kept = []
    for i, row in enumerate(rows[:keep], 1):
        dst = out / f"frame-{i}.jpg"
        with Image.open(row["file"]) as im:
            im.convert("RGB").save(dst, quality=92)
        kept.append({**row, "file": str(dst.relative_to(project)).replace("\\", "/")})
    return kept


def landscape_fill(src: Path, dst: Path, W: int = 1280, H: int = 720, side: str = "right") -> Path:
    """A portrait frame on a landscape canvas: the frame itself at one side, a blurred copy filling the rest."""
    from PIL import Image, ImageFilter
    with Image.open(src) as im:
        im = im.convert("RGB")
        bg = im.resize((W, int(W * im.height / im.width)), Image.LANCZOS)
        bg = bg.crop((0, (bg.height - H) // 2, W, (bg.height - H) // 2 + H)).filter(ImageFilter.GaussianBlur(28))
        fg = im.resize((int(H * im.width / im.height), H), Image.LANCZOS)
        x = W - fg.width - int(W * 0.06) if side == "right" else int(W * 0.06)
        bg.paste(fg, (x, 0))
        dst.parent.mkdir(parents=True, exist_ok=True)
        bg.save(dst, quality=92)
    return dst


def first_number(project: Path, sb: dict, brief: dict) -> str | None:
    """A figure worth a thumbnail: thumbnail.number, a stat scene's value, or digits in the title."""
    th = sb.get("thumbnail") or {}
    if th.get("number"):
        return str(th["number"])
    for s in sb.get("scenes", []):
        p = s.get("params") or {}
        if s.get("type") == "stat" and p.get("value") not in (None, ""):
            return f"{p['value']}{p.get('unit') or ''}"
    m = re.search(r"\d[\d.,]*\s?(?:%|x|X|k|K|m|M|s|min|days?|hours?)?", str(brief.get("title", "")) + " " + str(th.get("title", "")))
    return m.group(0).strip() if m else None


# ------------------------------------------------------------------ rendering one variant
def render_one(project: Path, name: str, params: dict, dest: Path, *, W: int | None = None, H: int | None = None, base: str = "thumbnail", safe: dict | None = None) -> dict:
    """Render the thumbnail scene with `params` through the stage and return the text it drew. The picture is written to dest."""
    tl = copy.deepcopy(dz.ensure_timeline(project, "thumbnail"))
    tl["platform"] = name
    if W and H:
        tl["W"], tl["H"] = W, H
        plat_tl = dz.ensure_timeline(project, base)
        tl["safe"] = safe or plat_tl.get("safe") or tl["safe"]
        tl["legibility"] = plat_tl.get("legibility") or tl.get("legibility")
    tl["captions"] = {**(tl.get("captions") or {}), "burn": False}
    tl["scenes"][0]["params"] = params
    f = project / "build" / f"timeline-{name}.json"
    save_json(f, tl)
    pdir = tdir(project) / "_probe"
    try:
        r = node("designprobe.mjs", project, "--platform", name, "--at", 0.5, "--mode", "render", "--out", pdir, capture=True, check=False)
        res = last_json_line(r.stdout or "") or {}
        if r.returncode != 0 or not res.get("probe"):
            raise FishError(f"thumbnail {name} did not render: {((r.stderr or '') + (r.stdout or ''))[-400:]}")
        fr = load_json(res["probe"])["frames"][0]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fr["file"], dest)
        return {"texts": fr["texts"], "tiles": fr.get("tiles") or [], "blocks": fr.get("blocks") or [], "issues": fr["issues"], "W": tl["W"], "H": tl["H"]}
    finally:
        f.unlink(missing_ok=True)
        shutil.rmtree(pdir, ignore_errors=True)
        shutil.rmtree(project / "build" / name, ignore_errors=True)


def save_small(png: Path) -> Path:
    """Keep a PNG when it is under the limit; else a JPEG of the same picture (a frame from video is photographic)."""
    from PIL import Image
    if png.stat().st_size <= MAX_BYTES * 0.9:
        return png
    jpg = png.with_suffix(".jpg")
    with Image.open(png) as im:
        for q in (92, 86, 78, 70):
            im.convert("RGB").save(jpg, quality=q, optimize=True)
            if jpg.stat().st_size <= MAX_BYTES * 0.9:
                break
    png.unlink()
    return jpg


# ------------------------------------------------------------------ make
ICON_DIR = SKILL / "node_modules" / "simple-icons"


def _icons_dir() -> Path:
    if not (ICON_DIR / "icons").is_dir():
        raise FishError("brand logos need the simple-icons package (CC0 icon files): run `npm install` in the skill folder")
    return ICON_DIR


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(t).lower())


def find_logos(text: str, limit: int = 8) -> list[dict]:
    """Search the simple-icons catalogue by title or slug: [{slug, title, hex}]."""
    data = load_json(_icons_dir() / "data" / "simple-icons.json")
    q = _norm(text)
    hits = [d for d in data if q and (q in _norm(d["title"]) or q in d["slug"])]
    hits.sort(key=lambda d: (_norm(d["title"]) != q, d["slug"] != q, len(d["title"])))
    return [{"slug": d["slug"], "title": d["title"], "hex": d["hex"]} for d in hits[:limit]]


def resolve_logos(items: list) -> list[dict]:
    """Slugs (or names) -> [{slug, title, hex, d, tile, fill}] for the stage. An unknown slug lists close matches."""
    from design import contrast, parse_color
    base = _icons_dir()
    data = {d["slug"]: d for d in load_json(base / "data" / "simple-icons.json")}
    out = []
    for it in items or []:
        slug = _norm(it["slug"] if isinstance(it, dict) else it)
        if slug not in data:
            near = ", ".join(x["slug"] for x in find_logos(slug)) or "none"
            raise FishError(f"no brand icon '{slug}' in simple-icons (some brands are not included). Close matches: {near}. Search: fishvideo thumb logos --find <name>")
        m = re.search(r' d="([^"]+)"', (base / "icons" / f"{slug}.svg").read_text(encoding="utf-8"))
        hexv = (it.get("hex") if isinstance(it, dict) and it.get("hex") else data[slug]["hex"]).lstrip("#")
        col = parse_color("#" + hexv)[:3]
        tile = "#16161a" if contrast(col, parse_color("#16161a")[:3]) >= 3 else "#ffffff"
        out.append({"slug": slug, "title": data[slug]["title"], "hex": hexv, "d": m.group(1), "tile": tile})
    return out


def logos_related(project: Path, logos: list[dict]) -> list[str]:
    """Brand titles that appear nowhere in the video's own words (brief, storyboard, facts). Logos must relate to the content."""
    sb = project / "storyboard.yaml"
    strip = lambda d: {k: v for k, v in (d or {}).items() if k not in ("thumbnail", "theme_overrides")}      # the thumbnail block itself proves nothing
    text = _norm(json.dumps(strip(load_yaml(sb) if sb.exists() else {})) + json.dumps(strip(project_config(project)["brief"])))
    return [lg["title"] for lg in logos if _norm(lg["title"]) not in text and lg["slug"] not in text]


def _is_image_path(project: Path, v: str) -> bool:
    return str(v).lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and (project / v).exists() and not is_screenshot_path(str(v))


def resolve_tiles(project: Path, p0: dict, sb: dict, brief: dict) -> tuple[list[dict], str]:
    """The tiles of the road thumbnail: brand logos (thumbnail.logos), explicit pictures (thumbnail.tiles), else licensed pictures
    from the project (assets/credits.json, then the images the storyboard shows). Never a screenshot. Returns (tiles, note)."""
    th = {**(brief.get("thumbnail") or {}), **(sb.get("thumbnail") or {}), **{k: v for k, v in p0.items() if k in ("logos", "tiles", "allow_unrelated_logos")}}
    tiles: list[dict] = []
    note = ""
    brands = [x for x in (th.get("logos") or []) if not (isinstance(x, str) and _is_image_path(project, x))]
    if brands:
        lg = resolve_logos(brands)
        bad = logos_related(project, lg)
        if bad and not th.get("allow_unrelated_logos"):
            raise FishError("logos that the video never mentions: " + ", ".join(bad) + ". Use only brands the video is about (trademarks stay with their owners), or set thumbnail.allow_unrelated_logos: true and say why.")
        tiles += [{"d": x["d"], "hex": x["hex"], "tile": x["tile"], "title": x["title"], "slug": x["slug"]} for x in lg]
        note = "logos: " + ", ".join(x["slug"] for x in lg)
    pics = [x["src"] if isinstance(x, dict) else x for x in (th.get("tiles") or [])]
    pics += [x for x in (th.get("logos") or []) if isinstance(x, str) and _is_image_path(project, x)]
    if not pics and not tiles:
        cred = load_json(project / "assets" / "credits.json", default=[]) if (project / "assets" / "credits.json").exists() else []
        pics = [c["file"] for c in cred if isinstance(c, dict) and c.get("file") and _is_image_path(project, c["file"])]
        used = []
        for sc in sb.get("scenes", []):
            for k in ("src", "image"):
                v = (sc.get("params") or {}).get(k)
                if isinstance(v, str) and _is_image_path(project, v) and v not in pics and v not in used:
                    used.append(v)
        pics += used
        note = "pictures from the project's licensed assets"
    for v in pics:
        if not _is_image_path(project, v):
            raise FishError(f"thumbnail tile {v!r}: not an image in the project (or it looks like a screenshot)")
        tiles.append({"src": v})
    if pics and tiles and not note:
        note = "pictures"
    if len(tiles) > 7:
        tiles = tiles[:7]
    return tiles, note


def plan(project: Path, n: int) -> tuple[list[dict], dict]:
    """The variants to draw: [{layout, name, params, note}] and the facts used."""
    cfg = project_config(project)
    brief = cfg["brief"]
    sbf = project / "storyboard.yaml"
    sb = load_yaml(sbf) if sbf.exists() else {}
    tl = dz.ensure_timeline(project, "thumbnail")
    p0 = dict(tl["scenes"][0]["params"] or {})
    p0.pop("layout", None)
    common = {k: p0[k] for k in ("title", "accent", "kicker", "badge") if p0.get(k)}
    if not common.get("title"):
        common["title"] = brief.get("title", "")
    hero = p0.get("image") or p0.get("hero")
    plats = [p for p in __import__("storyboard").platforms_of(cfg)]
    main = next((p for p in plats if (dz.ensure_timeline(project, p)["W"] >= dz.ensure_timeline(project, p)["H"])), plats[0])
    frames = best_frames(project, main) if not p0.get("frames_off") else []
    facts = {"frames": frames, "main": main, "hero": hero}
    portrait_src = bool(frames) and dz.ensure_timeline(project, main)["H"] > dz.ensure_timeline(project, main)["W"]
    sdir = tdir(project) / "src"

    def pic(i: int, fill: bool = False) -> str | None:
        if not frames:
            return None
        row = frames[min(i, len(frames) - 1)]
        if fill and portrait_src:
            out = landscape_fill(project / row["file"], sdir / f"fill-{i}.jpg")
            return str(out.relative_to(project)).replace("\\", "/")
        return row["file"]

    specs = []
    tiles, tnote = resolve_tiles(project, p0, sb, brief)
    if tiles:
        specs.append({"layout": "road", "params": {**common, "tiles": tiles, **{k: v for k, v in {"tag": p0.get("tag") or (sb.get("thumbnail") or {}).get("tag") or common.get("kicker"), "sub": p0.get("sub") or (sb.get("thumbnail") or {}).get("sub") or common.get("badge")}.items() if v}}, "note": tnote})
    specs.append({"layout": "subject", "params": {**common, **({"image": hero} if hero else {"image": pic(0)} if frames else {})}, "note": "subject: " + (hero or (frames[0]["scene"] if frames else "text only"))})
    if frames or hero:
        specs.append({"layout": "caption", "params": {**common, "image": pic(1 if len(frames) > 1 else 0, fill=True) or hero}, "note": "caption over frame " + (frames[min(1, len(frames) - 1)]["scene"] if frames else "")})
    num = first_number(project, sb, brief)
    if num:
        specs.append({"layout": "number", "params": {**common, "number": num, "label": p0.get("label") or common["title"]}, "note": f"number {num}"})
    b, a = p0.get("before"), p0.get("after")
    if (b and a) or frames or hero:
        specs.append({"layout": "split", "params": {**common, **({"before": b, "after": a} if b and a else {"image": hero or pic(0)})}, "note": "before/after" + ("" if b and a else " (the same picture, muted and live)")})
    if frames or hero:
        specs.append({"layout": "frame", "params": {**common, "image": pic(0) or hero}, "note": "best frame " + (frames[0]["scene"] if frames else "")})
    # an explicit params.layout in the storyboard leads
    lead = (sb.get("thumbnail") or {}).get("layout")
    specs.sort(key=lambda s: 0 if s["layout"] == lead else 1)
    return specs[: max(1, n)], facts


def make(project: Path, n: int = 5) -> dict:
    from PIL import Image, ImageDraw
    project = ensure_project(project)
    specs, facts = plan(project, n)
    out = tdir(project) / "variants"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    items = []
    for i, sp in enumerate(specs, 1):
        png = out / f"thumb-{i}-{sp['layout']}.png"
        try:
            info = render_one(project, f"thumbv{i}", {**sp["params"], "layout": sp["layout"]}, png)
        except FishError as e:
            warn(str(e))
            continue
        final = save_small(png)
        save_json(final.with_suffix(".json"), {"layout": sp["layout"], "image": sp["params"].get("image"), **info})
        items.append({"n": i, "layout": sp["layout"], "file": str(final.relative_to(project)).replace("\\", "/"), "bytes": final.stat().st_size, "note": sp["note"], "W": info["W"], "H": info["H"]})
        log(f"  {i}  {sp['layout']:<8} {final.name}  {final.stat().st_size / 1e3:.0f} KB  {sp['note']}")
    if not items:
        raise FishError("no thumbnail rendered")
    covers = make_covers(project, specs) if portrait_platforms(project) else []
    rep = {"variants": items, "covers": covers, "frames": [{k: v for k, v in f.items() if k != "file"} | {"file": f["file"]} for f in facts["frames"]]}
    save_json(tdir(project) / "variants.json", rep)
    rep["sheet"] = str(contact_sheet(project, items, covers))
    log(f"thumb make: {len(items)} variants, {len(covers)} covers -> {rep['sheet']}")
    return rep


STOPWORDS = set("a an the of and or but in on at to for with by from as is are was were be been it its this that these those vs".split())


def pick_accent(title: str, accent: str | None = None) -> str:
    """The KEY words of a headline, kept together as one phrase: the run of non-filler words (up to 3) that contains the author's accent
    word(s) ("Won" becomes "Emus Won"), or, when the accent is only filler ("The") or missing, the longest such run."""
    words = re.findall(r"\S+", title or "")
    norm = lambda w: re.sub(r"[^\w]", "", w.lower())                            # noqa: E731
    key = [norm(w) not in STOPWORDS for w in words]
    runs, i = [], 0
    while i < len(words):
        if key[i]:
            j = i
            while j < len(words) and key[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    runs = [(a, min(b, a + 3)) for a, b in runs]
    if accent:
        aw = [norm(w) for w in accent.split() if norm(w) not in STOPWORDS]
        for a, b in runs:
            if aw and all(w in [norm(x) for x in words[a:b]] for w in aw):
                return " ".join(words[a:b])
    if runs:
        a, b = max(runs, key=lambda r: sum(len(w) for w in words[r[0]:r[1]]))
        return " ".join(words[a:b])
    return " ".join(words[:2])


def _native(project: Path, src: str) -> tuple[int, int] | None:
    try:
        from PIL import Image
        with Image.open(Path(project) / src) as im:
            return im.size
    except Exception:                                                    # noqa: BLE001
        return None


def order_tiles(project: Path, tiles: list[dict]) -> list[dict]:
    """Picture tiles: the sharpest first (it becomes the big hero tile), at most 3. Logo tiles keep their order."""
    if not tiles or not all(t.get("src") for t in tiles):
        return tiles
    return sorted(tiles, key=lambda t: -min(_native(project, t["src"]) or (0, 0)))[:3]


def thumbnail(project: Path, covers: bool = True) -> dict:
    """THE required step. Draw the house `road` thumbnail (1280x720) and a 9:16 cover per vertical platform, check them, pick them."""
    project = ensure_project(project)
    cfg = project_config(project)
    brief = cfg["brief"]
    sbf = project / "storyboard.yaml"
    sb = load_yaml(sbf) if sbf.exists() else {}
    tl = dz.ensure_timeline(project, "thumbnail")
    p0 = dict(tl["scenes"][0]["params"] or {})
    p0.pop("layout", None)
    tiles, note = resolve_tiles(project, p0, sb, brief)
    if len(tiles) < 2:
        raise FishError("the thumbnail needs 2 or more tiles: brand logos the video is about (thumbnail.logos: [slug, ...] in storyboard.yaml; "
                        "find slugs with `fishvideo thumb logos --find <name>`) or licensed pictures (thumbnail.tiles: [assets/photo/a.jpg, ...], or assets in assets/credits.json). "
                        "A website screenshot is never used.")
    th = {**(brief.get("thumbnail") or {}), **(sb.get("thumbnail") or {})}
    params = {k: th[k] for k in ("title", "accent", "tag", "sub") if th.get(k)}      # what the author wrote for the thumbnail wins
    for k in ("title", "accent", "tag", "sub"):
        if p0.get(k) and k not in params:
            params[k] = p0[k]
    params.setdefault("title", brief.get("title", ""))
    if not params.get("tag") and th.get("kicker"):
        params["tag"] = th["kicker"]
    if not params.get("sub") and th.get("badge"):
        params["sub"] = th["badge"]
    params["tiles"] = order_tiles(project, tiles)
    params["accent"] = pick_accent(params.get("title", ""), params.get("accent"))
    out = tdir(project) / "variants"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    png = out / "thumb-1-road.png"
    info = render_one(project, "thumbroad", {**params, "layout": "road"}, png)
    final = save_small(png)
    save_json(final.with_suffix(".json"), {"layout": "road", "image": None, "tile_px": [_native(project, t["src"]) if t.get("src") else None for t in params["tiles"]], **info})
    items = [{"n": 1, "layout": "road", "file": str(final.relative_to(project)).replace("\\", "/"), "bytes": final.stat().st_size, "note": note, "W": info["W"], "H": info["H"]}]
    cv = make_covers(project, [{"layout": "road", "params": params}]) if covers and portrait_platforms(project) else []
    rep = {"variants": items, "covers": cv, "frames": []}
    save_json(tdir(project) / "variants.json", rep)
    save_json(tdir(project) / "pick.json", {"n": 1, "layout": "road", "file": items[0]["file"], **({"cover": cv[0]["n"]} if cv else {}), "inputs": json.loads(json.dumps(thumb_inputs(project), default=str))})
    res = check(project, only_pick=True)
    bad = [(r["name"], c) for r in res["results"] for c in r["checks"] if c["status"] == "FAIL"]
    for nm, c in bad:
        log(f"FAIL {nm}: {c['check']}: {c['detail']}")
    log(f"thumbnail: {final} ({note}); details build/thumbnail/check.md" + (f"; cover {cv[0]['file']}" if cv else ""))
    if bad:
        raise FishError("the thumbnail fails its check (above). Fix the tiles or the title and run `fishvideo thumbnail <dir>` again.")
    return rep


def thumb_inputs(project: Path) -> dict:
    """Everything the thumbnail is drawn from. `package` asks for a new thumbnail only when one of these changed."""
    project = Path(project)
    cfg = project_config(project)
    brief = cfg["brief"]
    sbf = project / "storyboard.yaml"
    sb = load_yaml(sbf) if sbf.exists() else {}
    th = {**(brief.get("thumbnail") or {}), **(sb.get("thumbnail") or {})}
    try:
        tiles, _ = resolve_tiles(project, {}, sb, brief)
    except FishError:
        tiles = []
    return {"title": th.get("title") or brief.get("title", ""), "thumbnail block": th, "theme": brief.get("theme"), "theme overrides": brief.get("theme_overrides"),
            "tiles": [t.get("src") or t.get("slug") for t in tiles],
            "tile files": {t["src"]: (project / t["src"]).stat().st_size for t in tiles if t.get("src") and (project / t["src"]).exists()}}


def package_gate(project: Path) -> list[str]:
    """Why `package` must refuse: no thumbnail, or one that fails its check. Each message names the command to run."""
    project = Path(project)
    td = tdir(project)
    cmd = f"fishvideo thumbnail {project.name}"
    if not (td / "variants.json").exists() or not (td / "pick.json").exists():
        return [f"no thumbnail: run `{cmd}` (the required step; it draws the house thumbnail and checks it)"]
    pk = load_json(td / "pick.json")
    errs = []
    if not (project / pk["file"]).exists():
        errs.append(f"the picked thumbnail file is missing: run `{cmd}`")
        return errs
    if portrait_platforms(project) and not pk.get("cover"):
        errs.append(f"this project has a 9:16 cut but no cover: run `{cmd}`")
    try:
        res = check(project, only_pick=True)
    except FishError as e:
        return [f"{e}: run `{cmd}`"]
    for r in res["results"]:
        for c in r["checks"]:
            if c["status"] == "FAIL":
                errs.append(f"thumbnail check failed ({r['name']}: {c['check']}: {c['detail']}). Fix it and run `{cmd}`")
    if pk.get("inputs"):
        now = json.loads(json.dumps(thumb_inputs(project), default=str))
        changed = [k for k in now if now[k] != pk["inputs"].get(k)]
        if changed:
            errs.append(f"the thumbnail's inputs changed ({', '.join(changed)}): run `{cmd}` again. (Other edits to brief.yaml or storyboard.yaml do not need a new thumbnail.)")
    return errs


def portrait_platforms(project: Path) -> list[str]:
    import storyboard as sbmod
    out = []
    for p in sbmod.platforms_of(project_config(project)):
        t = dz.ensure_timeline(project, p)
        if t["H"] > t["W"]:
            out.append(p)
    return out


def make_covers(project: Path, specs: list[dict]) -> list[dict]:
    out = tdir(project) / "covers"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    res, n = [], 0
    for plat in portrait_platforms(project):
        tl = dz.ensure_timeline(project, plat)
        for sp in specs:
            if sp["layout"] not in VERTICAL_LAYOUTS:
                continue
            params = dict(sp["params"])
            if sp["layout"] == "caption" and params.get("image"):    # a landscape-filled picture is the wrong shape here: use the frame itself
                params["image"] = re.sub(r"fill-(\d)", r"frame-\1", params["image"]).replace("fill-", "frame-")
                params["image"] = params["image"] if (project / params["image"]).exists() else sp["params"]["image"]
            n += 1
            png = out / f"cover-{plat}-{n}.png"
            try:
                info = render_one(project, f"thumbc{n}", {**params, "layout": sp["layout"]}, png, W=tl["W"], H=tl["H"], base=plat)
            except FishError as e:
                warn(str(e))
                continue
            final = save_small(png)
            save_json(final.with_suffix(".json"), {"layout": sp["layout"], "tile_px": [_native(project, t["src"]) if t.get("src") else None for t in params.get("tiles", [])], **info})
            res.append({"n": n, "platform": plat, "layout": sp["layout"], "file": str(final.relative_to(project)).replace("\\", "/"), "bytes": final.stat().st_size, "W": info["W"], "H": info["H"]})
            log(f"  cover {n}  {plat} {sp['layout']}  {final.name}")
    return res


def contact_sheet(project: Path, items: list[dict], covers: list[dict]) -> Path:
    from PIL import Image, ImageDraw
    f2 = dz.font(22, 800)
    cw, ch, pad, lab = 560, 315, 18, 54
    cols = 3
    rows = -(-len(items) // cols)
    cvh = 0
    if covers:
        cvw = 180
        cvh = int(cvw * 16 / 9) + lab
    W = pad + cols * (cw + pad)
    out = Image.new("RGB", (W, pad + rows * (ch + lab + pad) + (cvh + pad if covers else 0)), (20, 20, 22))
    d = ImageDraw.Draw(out)
    for i, it in enumerate(items):
        x, y = pad + (i % cols) * (cw + pad), pad + (i // cols) * (ch + lab + pad)
        with Image.open(project / it["file"]) as im:
            out.paste(im.convert("RGB").resize((cw, ch), Image.LANCZOS), (x, y))
        d.rectangle([x - 1, y - 1, x + cw, y + ch], outline=(70, 70, 76))
        d.text((x, y + ch + 8), f"{it['n']} · {it['layout']}", font=f2, fill=(245, 245, 245))
        d.text((x, y + ch + 32), f"{it['W']}x{it['H']} · {it['bytes'] / 1e3:.0f} KB", font=dz.font(16, 700), fill=(150, 150, 156))
    if covers:
        y = pad + rows * (ch + lab + pad)
        for i, cv in enumerate(covers[: W // (180 + pad)]):
            x = pad + i * (180 + pad)
            with Image.open(project / cv["file"]) as im:
                out.paste(im.convert("RGB").resize((180, int(180 * 16 / 9)), Image.LANCZOS), (x, y))
            d.text((x, y + int(180 * 16 / 9) + 8), f"cover {cv['n']} · {cv['layout']}", font=dz.font(18, 800), fill=(245, 245, 245))
    dest = tdir(project) / "variants-sheet.png"
    out.save(dest)
    return dest


# ------------------------------------------------------------------ check
def _row(check, status, detail, hard=False):
    return {"check": check, "status": status, "detail": detail, "hard": hard}


def check_image(path: Path, sidecar: dict | None = None, kind: str = "thumbnail") -> list[dict]:
    """Rows {check, status, detail, hard} for one thumbnail file. `sidecar` is the text the stage drew
    ({texts: [{text, box, px, color, words}]}); without it the text checks are skipped."""
    import numpy as np
    from PIL import Image
    path = Path(path)
    rows = []
    size = path.stat().st_size
    with Image.open(path) as im:
        W, H = im.size
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    rows.append(_row("file size", "PASS" if size <= MAX_BYTES else "FAIL", f"{size / 1e6:.2f} MB (limit 2 MB)", hard=True))
    want = 16 / 9 if kind == "thumbnail" else 9 / 16
    shape_ok = abs(W / H - want) < 0.02 and (W >= 1280 if kind == "thumbnail" else W >= 720)
    rows.append(_row("dimensions", "PASS" if shape_ok else "FAIL", f"{W}x{H}" + ("" if shape_ok else f" (want {'16:9, at least 1280 wide' if kind == 'thumbnail' else '9:16, at least 720 wide'})"), hard=True))
    shot = looks_like_screenshot(rgb) or is_screenshot_path(str((sidecar or {}).get("image") or ""))
    rows.append(_row("not a website screenshot", "FAIL" if shot else "PASS", "the picture is (or contains) a website screenshot: use the logos layout, a cut-out subject or a designed number instead" if shot else "no browser window or screenshot source found", hard=True))
    if (sidecar or {}).get("layout") == "road":
        W_ = W / 1280
        tiles, texts_ = (sidecar or {}).get("tiles") or [], (sidecar or {}).get("texts") or []
        rows.append(_row("tiles present", "PASS" if len(tiles) >= 2 else "FAIL", f"{len(tiles)} tiles" + ("" if len(tiles) >= 2 else " (the design needs at least 2 logos or pictures)"), hard=True))
        mg = LIMITS["tile_margin"] * W_
        out_ = [i for i, b in enumerate(tiles, 1) if b[0] < mg or b[1] < mg or b[0] + b[2] > W - mg or b[1] + b[3] > H - mg]
        rows.append(_row("tiles inside the frame", "FAIL" if out_ else "PASS", ("tile " + ", ".join(map(str, out_)) + f" is outside the safe margin ({LIMITS['tile_margin']} px at 1280 wide) of the frame edge") if out_ else "every tile is inside the frame with a safe margin", hard=True))
        m = LIMITS["tile_gap"] * W_
        hits = []
        for t in texts_:
            tx, ty, tw, th_ = t["box"]
            for i, b in enumerate(tiles, 1):
                if tx < b[0] + b[2] + m and tx + tw > b[0] - m and ty < b[1] + b[3] + m and ty + th_ > b[1] - m:
                    hits.append(f"{t['text'][:18]!r} / tile {i}")
        blocks = (sidecar or {}).get("blocks") or []
        heads = [t for t in texts_ if t.get("grp") == "head"]
        chip_hits = []
        for b in blocks:
            bx, by, bw, bh = b["box"]
            for t in heads:
                tx, ty, tw, th_ = t["box"]
                ty, th_ = ty + 0.12 * th_, 0.76 * th_                      # the glyphs, not the taller font box
                if tx < bx + bw - 2 and tx + tw > bx + 2 and ty < by + bh - 2 and ty + th_ > by + 2:
                    chip_hits.append(f"{b['name']} chip / {t['text'][:16]!r}")
        for t in [x for x in texts_ if x.get("grp") == "sub"]:
            tx, ty, tw, th_ = t["box"]
            for h in heads:
                hx, hy, hw, hh = h["box"]
                if tx < hx + hw and tx + tw > hx and ty < hy + hh - 4 and ty + th_ > hy + 4:
                    chip_hits.append(f"audience line / {h['text'][:16]!r}")
        rows.append(_row("words and chip do not overlap", "FAIL" if chip_hits else "PASS", ("overlap: " + ", ".join(chip_hits[:3])) if chip_hits else "the tag chip, the headline and the audience line are clear of each other", hard=True))
        tp = (sidecar or {}).get("tile_px") or []
        soft = []
        for i, (b, nat) in enumerate(zip(tiles, tp), 1):
            if nat and b[2] > LIMITS["tile_upscale"] * min(nat):
                soft.append(f"tile {i} is {int(b[2])} px from a {nat[0]}x{nat[1]} picture")
        rows.append(_row("tile pictures are sharp", "FAIL" if soft else "PASS", ("enlarged past " + str(LIMITS["tile_upscale"]) + "x: " + "; ".join(soft)) if soft else "no tile picture is enlarged past " + str(LIMITS["tile_upscale"]) + "x", hard=True))
        rows.append(_row("words clear of the tiles", "FAIL" if hits else "PASS", ("words touch or overlap a tile (gap under " + str(LIMITS["tile_gap"]) + " px): " + ", ".join(hits[:4])) if hits else f"every word is at least {LIMITS['tile_gap']} px from every tile (measured from the layout boxes)", hard=True))
    # light and colour
    g = (rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)) / 255
    mean, lo, hi = float(g.mean()), float(np.percentile(g, 2)), float(np.percentile(g, 98))
    r_ = rgb.astype(np.float32)
    mx, mn = r_.max(axis=2), r_.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    msat, vivid = float(sat.mean()), float(((sat > 0.5) & (mx > 90)).mean())
    ok = LIMITS["bright"][0] <= mean <= LIMITS["bright"][1]
    rows.append(_row("brightness", "PASS" if ok else "WARN", f"mean {mean:.2f}" + ("" if ok else " (too dark: it sinks into a dark feed)" if mean < LIMITS["bright"][0] else " (too bright: it glares in a light feed)")))
    rows.append(_row("tonal range", "PASS" if hi - lo >= LIMITS["range"] else "WARN", f"{hi - lo:.2f} between the 2nd and 98th percentile" + ("" if hi - lo >= LIMITS["range"] else " (flat: add a darker dark or a lighter light)")))
    rows.append(_row("saturation", "PASS" if msat >= LIMITS["sat"] or vivid >= LIMITS["vivid"] else "WARN", f"mean {msat:.2f}, vivid pixels {vivid * 100:.1f}%" + ("" if msat >= LIMITS["sat"] or vivid >= LIMITS["vivid"] else " (washed out: one strong colour carries a thumbnail)")))
    # the corner a feed covers with the duration (video thumbnails only)
    if kind == "thumbnail":
        x0, y0 = int(W * LIMITS["stamp"][0]), int(H * LIMITS["stamp"][1])
        zone = g[y0:, x0:]
        gx, gy = np.abs(np.diff(zone, axis=1))[:-1, :], np.abs(np.diff(zone, axis=0))[:, :-1]
        edges = float(((gx + gy) > 0.22).mean())
        hit = [t for t in (sidecar or {}).get("texts", []) if t["box"][0] + t["box"][2] > x0 and t["box"][1] + t["box"][3] > y0]
        bad = bool(hit) or edges > LIMITS["stamp_edges"]
        rows.append(_row("timestamp zone", "WARN" if bad else "PASS", ("text in the corner: " + ", ".join(repr(t["text"][:20]) for t in hit)) if hit else f"{edges * 100:.1f}% detail in the bottom-right corner" + (" (busy: the duration stamp will sit on detail)" if bad else " (clear)")))
    # text: size, contrast, survival
    texts = (sidecar or {}).get("texts")
    if texts is None:
        rows.append(_row("text", "PASS", "not measured (no text boxes recorded for this file); the pixel checks above still apply"))
        return rows
    big = max([t["px"] for t in texts] or [0])
    words = sum(t.get("words", len(t["text"].split())) for t in texts if t["px"] >= big * 0.5)
    extra = sum(t.get("words", len(t["text"].split())) for t in texts if t["px"] < big * 0.5)
    rows.append(_row("words on screen", "PASS" if words <= LIMITS["words_ok"] else "WARN", f"{words} words" + (f" (+{extra} in small type)" if extra else "") + ("" if words <= LIMITS["words_ok"] else f" (a thumbnail reads in a glance: {LIMITS['words_ok']} or fewer; cut to the 3 that matter)")))
    if not texts:
        return rows
    big = max(t["px"] for t in texts)
    main = [t for t in texts if t["px"] >= big * 0.5]
    for nm, (sw, sh) in SIZES.items():
        if kind != "thumbnail" and nm == "tiny":
            continue
        if kind != "thumbnail":      # a vertical cover is shown larger than a 16:9 thumbnail is wide (a shelf of tall cards)
            sh = 240 if nm == "feed" else 128
            sw = sh * 9 // 16
        s = sw / W
        px = big * s
        need = LIMITS["font_" + nm]
        floor = need if nm == "tiny" else LIMITS["font_floor"] if nm == "side" else LIMITS["font_floor"] * 1.5
        st = "PASS" if px >= need else "FAIL" if px < floor else "WARN"
        rows.append(_row(f"text size at {sw}x{sh}", st, f"the main text is {px:.1f} px high (font size; wants {need}+)" + ("" if st == "PASS" else f"; make it {int(need / s)}+ px on the {W}-wide original, or cut words so it can grow")))
        with Image.open(path) as im:
            small = np.asarray(im.convert("RGB").resize((sw, sh), Image.LANCZOS), dtype=np.uint8)
        worst, who = 99.0, ""
        for t in main:
            col = dz.parse_color(t.get("color"))
            b = [v * s for v in t["box"]]
            r = dz.text_contrast(small, b, col, tol=60)
            if r.get("ratio") is not None and r["ratio"] < worst:
                worst, who = r["ratio"], t["text"][:24]
        if worst < 99:
            st = "PASS" if worst >= LIMITS["contrast"] else "FAIL" if worst < LIMITS["contrast_floor"] else "WARN"
            rows.append(_row(f"words survive at {sw}x{sh}", st, f"{worst:.1f}:1 against what is behind {who!r} after shrinking" + ("" if st == "PASS" else " (the words blur into their background: a plate or a darker scrim behind them)")))
    return rows


def sidecar_of(project: Path, file: str) -> dict | None:
    j = (project / file).with_suffix(".json")
    return load_json(j) if j.exists() else None


def check(project: Path, files: list[Path] | None = None, only_pick: bool = True) -> dict:
    project = ensure_project(project)
    td = tdir(project)
    rep = load_json(td / "variants.json", default=None) if (td / "variants.json").exists() else None
    targets = []
    if files:
        targets = [{"name": f.name, "path": Path(f), "kind": "thumbnail"} for f in files]
    elif rep:
        pk = load_json(td / "pick.json") if (td / "pick.json").exists() else None
        for v in rep["variants"]:
            if pk and only_pick and v["n"] != pk["n"]:
                continue
            targets.append({"name": f"{v['n']} {v['layout']}", "path": project / v["file"], "kind": "thumbnail", "file": v["file"]})
        for cv in rep.get("covers", []):
            if pk and only_pick and cv["n"] != pk.get("cover"):
                continue
            targets.append({"name": f"cover {cv['n']} {cv['platform']} {cv['layout']}", "path": project / cv["file"], "kind": "cover", "file": cv["file"]})
    if not targets:
        raise FishError("no thumbnails to check: run `fishvideo thumb make` first, or pass --file")
    out = []
    for t in targets:
        side = sidecar_of(project, t["file"]) if t.get("file") else None
        rows = check_image(t["path"], side, t["kind"])
        status = "FAIL" if any(r["status"] == "FAIL" for r in rows) else "WARN" if any(r["status"] == "WARN" for r in rows) else "PASS"
        out.append({"name": t["name"], "file": str(t["path"]), "status": status, "checks": rows})
    res = {"results": out}
    save_json(td / "check.json", res)
    md = ["# Thumbnail check", ""]
    for r in out:
        md += [f"## {r['name']}: {r['status']}", "", "| check | status | detail |", "|---|---|---|", *[f"| {c['check']} | {c['status']} | {c['detail'].replace('|', '/')} |" for c in r["checks"]], ""]
    (td / "check.md").write_text("\n".join(md), encoding="utf-8")
    return res


def qa_rows(project: Path) -> list[dict]:
    """QA rows for the report. FAIL only for facts (size, shape); looks are a WARN. Nothing when no thumbnails were made."""
    td = Path(project) / "build" / "thumbnail"
    if not (td / "variants.json").exists():
        return []
    try:
        res = check(project)
    except Exception as e:  # a thumbnail check must never break QA
        return [{"check": "thumbnail", "status": "WARN", "detail": f"could not run: {str(e)[:120]}"}]
    rows = []
    for r in res["results"]:
        hard = [c for c in r["checks"] if c["status"] == "FAIL" and c.get("hard")]
        soft = [c for c in r["checks"] if c["status"] in ("WARN", "FAIL") and not (c["status"] == "FAIL" and c.get("hard"))]
        if hard:
            rows.append({"check": f"thumbnail {r['name']}", "status": "FAIL", "detail": "; ".join(f"{c['check']}: {c['detail']}" for c in hard)})
        elif soft:
            rows.append({"check": f"thumbnail {r['name']}", "status": "WARN", "detail": "; ".join(f"{c['check']}: {c['detail'][:70]}" for c in soft[:3]) + " (see build/thumbnail/check.md)"})
        else:
            rows.append({"check": f"thumbnail {r['name']}", "status": "PASS", "detail": "size, shape, legibility at 320 and 168 px all fine"})
    return rows


# ------------------------------------------------------------------ pick
def pick(project: Path, n: int, cover: int | None = None) -> dict:
    project = ensure_project(project)
    td = tdir(project)
    if not (td / "variants.json").exists():
        raise FishError("no variants yet: run `fishvideo thumb make` first")
    rep = load_json(td / "variants.json")
    v = next((x for x in rep["variants"] if x["n"] == n), None)
    if not v:
        raise FishError(f"no variant {n} (have {', '.join(str(x['n']) for x in rep['variants'])})")
    rec = {"n": n, "layout": v["layout"], "file": v["file"]}
    if cover is not None:
        cv = next((x for x in rep.get("covers", []) if x["n"] == cover), None)
        if not cv:
            raise FishError(f"no cover {cover} (have {', '.join(str(x['n']) for x in rep.get('covers', [])) or 'none'})")
        rec["cover"] = cover
    elif rep.get("covers"):
        same = next((x for x in rep["covers"] if x["layout"] == v["layout"]), rep["covers"][0])
        rec["cover"] = same["n"]
    save_json(td / "pick.json", rec)
    log(f"picked variant {n} ({v['layout']}): {v['file']}" + (f", cover {rec['cover']}" if rec.get("cover") else ""))
    return rec


def ship(project: Path, dest: Path) -> list[str]:
    """Copy the picked thumbnail (or the first variant), the variants sheet, the feed mock-ups and the check results into a package.
    Does nothing when no variants were made, so existing packages are unchanged."""
    project = Path(project)
    td = project / "build" / "thumbnail"
    if not (td / "variants.json").exists():
        return []
    rep = load_json(td / "variants.json")
    pk = load_json(td / "pick.json") if (td / "pick.json").exists() else None
    v = next((x for x in rep["variants"] if pk and x["n"] == pk["n"]), rep["variants"][0])
    out = Path(dest) / "thumbnails"
    out.mkdir(parents=True, exist_ok=True)
    shipped = []
    src = project / v["file"]
    for old in out.glob("thumbnail-1280x720.*"):
        old.unlink()
    tgt = out / f"thumbnail-1280x720{src.suffix}"
    shutil.copy2(src, tgt)
    shipped.append(tgt.name)
    cv = next((x for x in rep.get("covers", []) if pk and x["n"] == pk.get("cover")), (rep.get("covers") or [None])[0])
    if cv:
        for old in out.glob(f"cover-{cv['platform']}.*"):
            old.unlink()
        t2 = out / f"cover-{cv['platform']}{Path(cv['file']).suffix}"
        shutil.copy2(project / cv["file"], t2)
        shipped.append(t2.name)
    for name, as_ in (("variants-sheet.png", "thumbnail-variants.png"), ("feed-light.png", "thumbnail-feed-light.png"), ("feed-dark.png", "thumbnail-feed-dark.png")):
        if (td / name).exists():
            shutil.copy2(td / name, out / as_)
            shipped.append(as_)
    try:
        check(project, only_pick=True)
    except FishError:
        pass
    for name, as_ in (("check.md", "thumbnail-check.md"), ("check.json", "thumbnail-check.json")):
        if (td / name).exists():
            shutil.copy2(td / name, out / as_)
            shipped.append(as_)
    qa = Path(dest) / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    for f in sorted((project / "build").glob("*/design-lint.md")):
        shutil.copy2(f, qa / f"frame-lint-{f.parent.name}.md")
        shipped.append(f"qa/frame-lint-{f.parent.name}.md")
    return shipped


# ------------------------------------------------------------------ feed mock-up
def feed_sheet(project: Path) -> list[Path]:
    """A mock feed, light and dark: the variants among neutral grey placeholders at the sizes a feed shows."""
    from PIL import Image, ImageDraw
    project = ensure_project(project)
    td = tdir(project)
    if not (td / "variants.json").exists():
        raise FishError("no variants yet: run `fishvideo thumb make` first")
    rep = load_json(td / "variants.json")
    vs = rep["variants"]
    outs = []
    for theme, bgc, ink, bar, greys in (("light", (250, 250, 250), (24, 24, 26), (214, 214, 218), [(176, 176, 180), (160, 162, 168), (190, 188, 184)]),
                                        ("dark", (15, 15, 17), (236, 236, 240), (56, 56, 62), [(74, 74, 80), (62, 64, 70), (84, 82, 78)])):
        cw, ch, pad, meta = 320, 180, 20, 74
        cols = 3
        # every variant appears, spread out among the placeholders
        seq = []
        gi = 0
        vi = 0
        total = len(vs) * 2 + 1
        for i in range(total):
            if i % 2 == 1 and vi < len(vs):
                seq.append(("ours", vs[vi]))
                vi += 1
            else:
                seq.append(("grey", gi))
                gi += 1
        rows = -(-len(seq) // cols)
        side_w = 168 + 2 * pad + 190
        W = pad + cols * (cw + pad) + side_w
        H = pad + 54 + rows * (ch + meta + pad)
        img = Image.new("RGB", (W, H), bgc)
        d = ImageDraw.Draw(img)
        d.text((pad, pad), f"mock feed · {theme} · real display sizes: 320x180 and 168x94", font=dz.font(18, 700), fill=ink)
        for i, (kind, v) in enumerate(seq):
            x, y = pad + (i % cols) * (cw + pad), pad + 54 + (i // cols) * (ch + meta + pad)
            if kind == "ours":
                with Image.open(project / v["file"]) as im:
                    img.paste(im.convert("RGB").resize((cw, ch), Image.LANCZOS), (x, y))
            else:
                g = greys[v % len(greys)]
                d.rounded_rectangle([x, y, x + cw, y + ch], radius=8, fill=g)
            tw = 44
            d.rounded_rectangle([x + cw - tw - 6, y + ch - 24, x + cw - 6, y + ch - 6], radius=4, fill=(12, 12, 14))      # the duration stamp
            d.text((x + cw - tw, y + ch - 22), "12:34", font=dz.font(13, 700), fill=(240, 240, 240))
            d.ellipse([x, y + ch + 12, x + 36, y + ch + 48], fill=bar)
            if kind == "ours":
                d.text((x + 48, y + ch + 12), f"variant {v['n']} · {v['layout']}", font=dz.font(16, 800), fill=ink)
            else:
                d.rounded_rectangle([x + 48, y + ch + 14, x + cw - 20, y + ch + 26], radius=5, fill=bar)
            d.rounded_rectangle([x + 48, y + ch + 34, x + int(cw * 0.7), y + ch + 44], radius=5, fill=bar)
            d.rounded_rectangle([x + 48, y + ch + 52, x + int(cw * 0.45), y + ch + 62], radius=5, fill=bar)
        # a sidebar of small ones
        sx = pad + cols * (cw + pad) + pad
        d.text((sx, pad + 54 - 28), "up next · 168x94", font=dz.font(15, 700), fill=ink)
        for j in range(min(6, len(seq))):
            y = pad + 54 + j * (94 + 18)
            v = vs[j % len(vs)] if j % 2 == 0 else None
            if v:
                with Image.open(project / v["file"]) as im:
                    img.paste(im.convert("RGB").resize((168, 94), Image.LANCZOS), (sx, y))
            else:
                d.rounded_rectangle([sx, y, sx + 168, y + 94], radius=6, fill=greys[j % len(greys)])
            d.rounded_rectangle([sx + 176, y + 4, sx + 176 + 150, y + 14], radius=5, fill=bar)
            d.rounded_rectangle([sx + 176, y + 22, sx + 176 + 100, y + 32], radius=5, fill=bar)
            if v:
                d.text((sx + 176, y + 44), f"variant {v['n']}", font=dz.font(14, 800), fill=ink)
        dest = td / f"feed-{theme}.png"
        img.save(dest)
        outs.append(dest)
    return outs


# ------------------------------------------------------------------ subject cut-out with outline and glow
def glow_cutout(src: Path, dst: Path | None = None, outline: int = 10, glow: int = 34, color: str | None = None, outline_color: str = "#ffffff", cut: bool = True) -> Path:
    """A subject with an outline and a glow, as a transparent PNG. The background is removed with `assets cutout`
    (rembg) unless the picture already has transparency; `cut=False` keeps the picture as it is."""
    import numpy as np
    from PIL import Image, ImageFilter
    import assets as assetsmod
    src = Path(src)
    if not src.exists():
        raise FishError(f"{src} not found")
    dst = Path(dst) if dst else src.with_name(f"{src.stem}-glow.png")
    with Image.open(src) as im:
        has_alpha = im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema()[0] < 250
    work = src
    if cut and not has_alpha:
        tmp = dst.with_name(f"{dst.stem}-cut.png")
        if assetsmod.cutout(src, tmp) is None:
            raise FishError("the background could not be removed (is rembg installed? `pip install \"rembg[cpu]\"`); pass a PNG with transparency or --no-cut")
        work = tmp
    subj = Image.open(work).convert("RGBA")
    a = subj.getchannel("A")
    pad = outline + glow * 2 + 4
    canvas = (subj.width + 2 * pad, subj.height + 2 * pad)
    big = Image.new("L", canvas, 0)
    big.paste(a, (pad, pad))
    body = Image.new("RGBA", canvas, (0, 0, 0, 0))
    body.paste(subj, (pad, pad))

    def grow(mask, r):
        # a round dilation: blur, then keep everything the blur touched
        return mask.filter(ImageFilter.GaussianBlur(max(0.1, r / 2))).point(lambda v: 255 if v > 8 else 0).filter(ImageFilter.GaussianBlur(1.2)) if r > 0 else mask

    ring = grow(big, outline)
    col = dz.parse_color(color) if color else None
    if col is None:
        try:
            col = dz.parse_color((project_config(src.parent.parent if (src.parent.parent / "brief.yaml").exists() else src.parent)["brief"].get("brand") or {}).get("colors", {}).get("accent"))
        except Exception:
            col = None
    col = col or (255, 90, 31, 1.0)
    oc = dz.parse_color(outline_color) or (255, 255, 255, 1.0)
    halo = ring.filter(ImageFilter.GaussianBlur(glow))
    halo = halo.point(lambda v: min(255, int(v * 1.6)))
    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    out.paste(Image.new("RGBA", canvas, tuple(int(c) for c in col[:3]) + (255,)), (0, 0), halo)
    out.paste(Image.new("RGBA", canvas, tuple(int(c) for c in oc[:3]) + (255,)), (0, 0), ring)
    out.alpha_composite(body)
    box = out.getchannel("A").point(lambda v: 255 if v > 4 else 0).getbbox()
    if box:
        out = out.crop(box)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, optimize=True)
    if work != src:
        Path(work).unlink(missing_ok=True)
    log(f"cutout with outline {outline} px and glow {glow} px -> {dst}")
    return dst


# ------------------------------------------------------------------ CLI
def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fishvideo thumb", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make"); p.add_argument("project"); p.add_argument("--variants", type=int, default=5)
    p = sub.add_parser("check"); p.add_argument("project"); p.add_argument("--file", action="append", default=None); p.add_argument("--all", action="store_true")
    p = sub.add_parser("sheet"); p.add_argument("project")
    p = sub.add_parser("pick"); p.add_argument("project"); p.add_argument("n", type=int); p.add_argument("--cover", type=int, default=None)
    p = sub.add_parser("cutout"); p.add_argument("image"); p.add_argument("--out", default=None); p.add_argument("--outline", type=int, default=10)
    p.add_argument("--glow", type=int, default=34); p.add_argument("--color", default=None); p.add_argument("--no-cut", action="store_true")
    p = sub.add_parser("logos"); p.add_argument("project", nargs="?"); p.add_argument("--find", default=None); p.add_argument("--slugs", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "logos":
        if a.find:
            for h in find_logos(a.find):
                log(f"{h['slug']:<24} {h['title']:<28} #{h['hex']}")
            return 0
        slugs = [x for x in (a.slugs or "").split(",") if x]
        lg = resolve_logos(slugs)
        for x in lg:
            log(f"ok  {x['slug']:<22} {x['title']}")
        if a.project:
            bad = logos_related(Path(a.project), lg)
            if bad:
                log("NOT RELATED to the video (never mentioned): " + ", ".join(bad))
                return 1
        log("Logos are trademarks of their owners. Use only brands the video is about. Add to storyboard.yaml: thumbnail: {logos: [" + ", ".join(x["slug"] for x in lg) + "]}")
        return 0
    if a.cmd == "make":
        make(Path(a.project), a.variants)
        log("look at them, then: fishvideo thumb check <dir> --all   and   fishvideo thumb pick <dir> N")
    elif a.cmd == "check":
        res = check(Path(a.project), [Path(f) for f in a.file] if a.file else None, only_pick=not a.all)
        bad = 0
        for r in res["results"]:
            log(f"{r['status']:<4} {r['name']}")
            for c in r["checks"]:
                if c["status"] != "PASS":
                    log(f"       {c['status']:<4} {c['check']:<28} {c['detail']}")
            bad += r["status"] == "FAIL"
        log(f"details: build/thumbnail/check.md")
        return 1 if bad else 0
    elif a.cmd == "sheet":
        for f in feed_sheet(Path(a.project)):
            log(f"feed: {f}")
    elif a.cmd == "pick":
        pick(Path(a.project), a.n, a.cover)
    elif a.cmd == "cutout":
        glow_cutout(Path(a.image), Path(a.out) if a.out else None, a.outline, a.glow, a.color, cut=not a.no_cut)
        log("use it: thumbnail: {image: <that file>, baked: true} in storyboard.yaml (baked: the outline and glow are already in the picture)")
    return 0


def thumbnail_cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fishvideo thumbnail", description="The required thumbnail step: the house road design, checked and picked.")
    ap.add_argument("project"); ap.add_argument("--no-covers", action="store_true")
    a = ap.parse_args(argv)
    thumbnail(Path(a.project), covers=not a.no_covers)
    return 0


if __name__ == "__main__":
    main_guard(cli)
