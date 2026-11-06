"""Themes: a whole look (type, texture, layout, motion, colour) in one id.

    fishvideo themes                         list every theme: genre, mode, type pairing, texture, layout, motion
    fishvideo themes show <id>               one theme in full
    fishvideo themes preview [--out DIR] [--only id,id]   one gallery image per theme (+ gallery.png), drawn with generated placeholders
    fishvideo themes apply <dir> <id>        write `theme: <id>` into the project's brief

A brief with `theme: <id>` gets that theme's colours, fonts, texture, layout tokens and caption look
(config/themes.yaml). `theme_overrides:` changes single values (colors, fonts, texture, layout, captions) and wins.
A brief without `theme:` is untouched, so existing projects render exactly as before.
Previews use generated placeholder pictures only: no photograph is bundled.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from fvcore import SKILL, FishError, load_yaml, log, main_guard, save_yaml

TEXTURE_ALL = {"paper", "grain", "clean", "grid", "blueprint", "halftone", "scanlines", "notebook", "dots", "sunburst", "stripes", "film"}
_CFG = None


def config() -> dict:
    global _CFG
    if _CFG is None:
        _CFG = load_yaml(SKILL / "config" / "themes.yaml")
    return _CFG


def all_themes() -> dict:
    return config()["themes"]


def get(theme_id: str) -> dict:
    t = all_themes().get(theme_id)
    if t is None:
        raise FishError(f"unknown theme '{theme_id}': one of {', '.join(all_themes())} (fishvideo themes)")
    return t


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def resolve(brief: dict) -> dict | None:
    """The brief's theme as stage inputs: {id, colors, fonts, mode, texture, layout, captions, caption_style} or None."""
    tid = brief.get("theme")
    if not tid:
        return None
    t = _merge(get(tid), brief.get("theme_overrides") or {})
    lay = dict(t.get("layout") or {})
    for k, v in (t.get("motion") or {}).items():
        lay[k] = v
    cap = dict(t.get("captions") or {})
    style = cap.pop("style", None)
    return {"id": tid, "colors": dict(t["colors"]), "fonts": dict(t["fonts"]), "mode": t.get("mode", "light"), "texture": t.get("texture"),
            "layout": lay, "captions": cap, "caption_style": style}


def apply_to_brief(brief: dict) -> dict:
    """Fill brand + texture + captions from the theme (the theme wins over the template defaults; overrides win over the theme)."""
    r = resolve(brief)
    if not r:
        return brief
    b = brief.setdefault("brand", {})
    b["colors"] = {**r["colors"]}
    b["fonts"] = {**(b.get("fonts") or {}), **r["fonts"]}
    b["mode"] = r["mode"]
    if r["texture"]:
        brief["texture"] = r["texture"]
    if r["caption_style"]:
        brief.setdefault("captions", {})["style"] = r["caption_style"]
    return brief


def rows() -> list[dict]:
    out = []
    for k, t in all_themes().items():
        lay, mo = t.get("layout") or {}, t.get("motion") or {}
        out.append({"id": k, "label": t["label"], "genre": t["genre"], "mode": t["mode"], "type": t["fonts"]["display"] + " + " + t["fonts"]["sans"],
                    "texture": t["texture"], "layout": f"{lay.get('kicker')}/{lay.get('card')}", "motion": f"x{mo.get('speed', 1)}", "best_for": t["best_for"]})
    return out


def options() -> list[dict]:
    """The interview's theme question: label, value, description (with the look in a few words)."""
    return [{"label": r["label"], "value": r["id"], "description": f"{r['best_for']}. {r['type']}, {r['texture']} texture, {r['mode']}, {r['layout']} layout, motion {r['motion']}"} for r in rows()]


# ------------------------------------------------------------------ fonts must be installed (never a silent fallback)
def missing_fonts(brief: dict | None = None) -> list[tuple[str, str]]:
    """[(family, missing file)] for the fonts a project's theme asks for (all themes when brief is None) that npm has not installed."""
    import re
    css = (SKILL / "scripts" / "stage" / "fonts.css").read_text(encoding="utf-8")
    faces = re.findall(r'font-family: "([^"]+)";.*?src: url\(([^)]+)\)', css)
    if brief is None:
        want = {f for t in all_themes().values() for f in t["fonts"].values()}
    else:
        r = resolve(brief)
        want = set((r or {}).get("fonts", {}).values()) | set(((brief.get("brand") or {}).get("fonts") or {}).values())
    out = []
    for fam, url in faces:
        if fam in want:
            f = SKILL / url.replace("/skill/", "", 1)
            if not f.exists() and (fam, str(f.relative_to(SKILL))) not in out:
                out.append((fam, str(f.relative_to(SKILL))))
    return out


def check_fonts(brief: dict) -> None:
    miss = missing_fonts(brief)
    if miss:
        fams = sorted({m[0] for m in miss})
        raise FishError(f"theme fonts are not installed: {', '.join(fams)} (first missing file: {miss[0][1]}). The renderer would silently fall back to another typeface. "
                        "Run `npm install` in the skill folder (it fetches every @fontsource package), then try again.")


# ------------------------------------------------------------------ preview
def _placeholder(path: Path, theme: dict, kind: int) -> None:
    """A generated picture (gradient, sun and hills): stands in for a real photo; nothing is copied from anywhere."""
    from PIL import Image, ImageDraw
    c = theme["colors"]
    W, H = 1600, 1000
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    top, bot = (c["accent"], c["bg"]) if kind % 2 == 0 else (c["accent2"], c["surface"])
    def hx(s):
        s = s.lstrip("#"); return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    a, b = hx(top), hx(bot)
    for y in range(H):
        f = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3)))
    d.ellipse([W * 0.62, H * 0.12, W * 0.62 + 260, H * 0.12 + 260], fill=hx(c["ink"]))
    for i, (x0, h0) in enumerate([(-100, 0.55), (350, 0.62), (800, 0.5), (1150, 0.6)]):
        d.polygon([(x0, H), (x0 + 450, H * h0), (x0 + 900, H)], fill=tuple(int(v * (0.45 - i * 0.04)) for v in hx(c["ink"])) if False else tuple(max(0, int(v * 0.35)) for v in hx(c["bg"])))
    im.save(path, quality=90)


def preview(out: Path, only: list[str] | None = None, platform: str = "youtube", scale: float = 0.5) -> list[Path]:
    """Render one gallery image per theme: a photo-led story frame beside a cards frame, stacked, with the theme name. Returns the files."""
    from PIL import Image, ImageDraw
    import design as dz
    import storyboard as sbmod
    from fvcore import node
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    ids = only or list(all_themes())
    files = []
    for tid in ids:
        th = get(tid)
        with tempfile.TemporaryDirectory(prefix="fvtheme-") as td:
            proj = Path(td) / "p"
            (proj / "assets").mkdir(parents=True)
            _placeholder(proj / "assets" / "a.jpg", th, 0)
            _placeholder(proj / "assets" / "b.jpg", th, 1)
            save_yaml(proj / "brief.yaml", {"title": th["label"], "prompt": "theme preview", "goal": "explain", "structure": "explainer", "length": 12, "platforms": [platform],
                                            "language": "en-US", "theme": tid, "brand": {"name": ""}, "voice": {"provider": "none"}, "captions": {"burn": False}})
            save_yaml(proj / "storyboard.yaml", {"title": th["label"], "bpm": 120, "scenes": [
                {"id": "photo", "type": "story", "bars": 2, "say": "", "params": {"src": "assets/a.jpg", "kicker": th["genre"].upper(), "lines": [{"text": "Photo leads the *frame*", "at": 0.1, "size": 104}, {"text": th["label"], "at": 0.3, "size": 70, "dim": True}]}},
                {"id": "cards", "type": "cards", "bars": 2, "say": "", "params": {"kicker": "Layout", "title": "Cards and *type*", "items": [{"tag": "01", "t": "One", "d": "First idea"}, {"tag": "02", "t": "Two", "d": "Second idea"}, {"tag": "03", "t": "Three", "d": "Third idea"}], "cols": 3}},
            ]})
            sbmod.build(proj, quiet=True)
            r = node("stills.mjs", proj, "--platform", platform, "--scenes", capture=True, check=False)
            stills = sorted((proj / "build" / platform / "stills").glob("*.png")) + sorted((proj / "build" / platform / "stills").glob("*.jpg"))
            if r.returncode != 0 or len(stills) < 2:
                raise FishError(f"theme preview for {tid} failed: {((r.stderr or '') + (r.stdout or ''))[-300:]}")
            ims = [Image.open(f).convert("RGB") for f in stills[:2]]
            w = 960
            ims = [i.resize((w, int(i.height * w / i.width))) for i in ims]
            tile = Image.new("RGB", (w, sum(i.height for i in ims) + 54), th["colors"]["bg"])
            y = 54
            for i in ims:
                tile.paste(i, (0, y)); y += i.height
            dr = ImageDraw.Draw(tile)
            dr.rectangle([0, 0, w, 54], fill=th["colors"]["surface"])
            dr.text((16, 16), f"{tid}  |  {th['genre']}  |  {th['fonts']['display']} + {th['fonts']['sans']}  |  {th['texture']}", fill=th["colors"]["ink"])
            dest = out / f"theme-{tid}.png"
            tile.save(dest)
            files.append(dest)
            log(f"  {tid:<16} -> {dest}")
    if len(files) > 1:
        ims = [Image.open(f) for f in files]
        cols = 2
        rowsn = (len(ims) + cols - 1) // cols
        cw = 640
        thumbs = [i.resize((cw, int(i.height * cw / i.width))) for i in ims]
        ch = max(t.height for t in thumbs)
        sheet = Image.new("RGB", (cols * cw + (cols + 1) * 12, rowsn * ch + (rowsn + 1) * 12), "#202124")
        for n, t in enumerate(thumbs):
            sheet.paste(t, (12 + (n % cols) * (cw + 12), 12 + (n // cols) * (ch + 12)))
        g = out / "gallery.png"
        sheet.save(g)
        files.append(g)
        log(f"gallery: {g}")
    return files


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fishvideo themes", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list")
    p = sub.add_parser("show"); p.add_argument("id")
    p = sub.add_parser("preview"); p.add_argument("--out", default="theme-gallery"); p.add_argument("--only", default=None); p.add_argument("--platform", default="youtube")
    p = sub.add_parser("apply"); p.add_argument("project"); p.add_argument("id")
    a = ap.parse_args(argv)
    if a.cmd in (None, "list"):
        log(f"{len(all_themes())} themes (fishvideo themes show <id>, fishvideo themes preview):")
        for r in rows():
            log(f"  {r['id']:<16} {r['genre']:<12} {r['mode']:<5} {r['type']:<34} {r['texture']:<10} {r['layout']:<14} {r['motion']:<6} {r['best_for'][:60]}")
    elif a.cmd == "show":
        import json
        log(json.dumps(get(a.id), indent=1))
    elif a.cmd == "preview":
        preview(Path(a.out), a.only.split(",") if a.only else None, a.platform)
    elif a.cmd == "apply":
        get(a.id)
        f = Path(a.project) / "brief.yaml"
        b = load_yaml(f)
        b["theme"] = a.id
        save_yaml(f, b)
        log(f"theme {a.id} set in {f}")
    return 0


if __name__ == "__main__":
    main_guard(cli)
