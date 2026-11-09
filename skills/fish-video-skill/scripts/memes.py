"""Memes: find them, cut them, caption them, and keep their licences honest.

    python scripts/memes.py sources   [--region us|in|world]            where memes come from, and how each source may be used
    python scripts/memes.py templates <project> [query] [--gif] [-n 12]  Imgflip templates (candidates; `assets get` downloads)
    python scripts/memes.py trending  <project> [--region in] [-n 10]    research only: what is being memed now -> research/memes.md
    python scripts/memes.py films     <project> <query> [--region in] [--before 1931] [-n 12]   public-domain and CC film
    python scripts/memes.py add       <project> <file-or-url> --title T [--source vlipsy|imgflip|own|...] [--source-url U]
                                      [--license L] [--author A] [--id name] [--accept-risk]
    python scripts/memes.py sheet     <video> [--out sheet.png] [--every 2] [--from 0] [--to 60] [--cols 6]
    python scripts/memes.py cut       <project> <video> <clip_id> --start S --dur D [--aspect 16:9] [--focus x,y] [--grade bw] [--sharpen]
    python scripts/memes.py caption   <image> <out.png> [--top "..."] [--bottom "..."] [--width 1080]
    python scripts/memes.py lint      <project>

Licence tiers (fvnet): `safe`, `platform`, `unverified`. Meme templates and viral clips are almost always
someone's copyrighted picture, so they are `unverified`: `assets get`, `memes add` and `memes cut` refuse
them unless the brief says `memes.policy: viral` (interview question `memes`) or --accept-risk is passed.
Nothing here automates a source whose terms forbid it: see config/memes.yaml for each source's route.
"""
from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import urllib.parse
from pathlib import Path

from fvcore import SKILL, FishError, ensure_project, ffmpeg_bin, load_json, load_yaml, log, main_guard, mmss, node, run, save_json, secret, slugify, warn
import fvnet
from fvnet import add_credit, norm_license

IMGFLIP = "https://api.imgflip.com"
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv", ".ogv", ".m4v")
UNLICENSED = "No licence (a meme template: the original picture belongs to its owner)"


def sources_cfg() -> dict:
    return load_yaml(SKILL / "config" / "memes.yaml")


# ------------------------------------------------------------------ sources
def sources(region: str | None = None) -> list[dict]:
    """The source list for a region, each with the URL to open and the route the skill may take."""
    cfg = sources_cfg()
    if region and region not in cfg["regions"]:
        raise FishError(f"region must be one of {sorted(cfg['regions'])}")
    out = []
    for s in cfg["sources"]:
        urls = s.get("urls") or {}
        url = urls.get(region) if region else None
        out.append({"id": s["id"], "name": s["name"], "what": s["what"], "access": s["access"], "risk": s["risk"],
                    "url": url or urls.get("world") or next(iter(urls.values()), ""), "regional": bool(url), "tool": s["tool"], "mcp": s.get("mcp"), "evidence": s["evidence"]})
    return out


def print_sources(region: str | None = None) -> None:
    cfg = sources_cfg()
    log(f"Meme sources{' for ' + cfg['regions'][region]['label'] if region else ''} (terms checked {cfg['checked']}):")
    for s in sources(region):
        log(f"\n  {s['name']}  [{s['access'].upper()}, risk: {s['risk']}]  {s['what']}")
        log(f"    open: {s['url']}" + ("" if s["regional"] or not region else "   (no page for this region)"))
        if s["mcp"]:
            log(f"    MCP:  claude mcp add --transport http {s['id']} {s['mcp']}")
        log(f"    use:  {s['tool']}")
        log(f"    why:  {s['evidence']}")


# ------------------------------------------------------------------ templates (Imgflip)
def _template(m: dict) -> dict:
    return {"id": f"imgflip-{fvnet.safe_name(m['id'])}", "provider": "imgflip", "kind": "meme", "title": str(m.get("name") or "")[:140],
            "url": f"https://imgflip.com/memetemplate/{urllib.parse.quote(str(m['id']))}", "download_url": m.get("url"), "preview_url": m.get("url"),
            "width": m.get("width"), "height": m.get("height"), "duration": None, "author": "unknown (uploaded to Imgflip)", "author_url": "",
            "license": UNLICENSED, "license_url": "", "attribution_required": False, "risk": "unverified",
            "captions": m.get("captions"), "box_count": m.get("box_count")}


def template_search(q: str | None = None, gif: bool = False, n: int = 12) -> list[dict]:
    """Imgflip templates, most-captioned first. Without a key: the public top list, filtered by the query.
    With IMGFLIP_API_KEY (a paid plan) and a query: the full database."""
    key = secret("IMGFLIP_API_KEY")
    kind = "gif" if gif else "image"
    if key and q:
        d = fvnet.fetch_json(f"{IMGFLIP}/search_memes", {"query": q, "type": kind}, {"Authorization": f"Bearer {key}"})
        memes = (d.get("data") or {}).get("memes") or []
    else:
        d = fvnet.fetch_json(f"{IMGFLIP}/get_memes", {"type": kind} if gif else None)
        memes = (d.get("data") or {}).get("memes") or []
        if q:
            words = [w for w in re.split(r"\W+", q.lower()) if w]
            memes = [m for m in memes if all(w in str(m.get("name", "")).lower() for w in words)]
    if not d.get("success", True):
        raise fvnet.NetError(f"imgflip: {d.get('error_message') or 'request refused'}")
    memes.sort(key=lambda m: -(m.get("captions") or 0))
    return [_template(m) for m in memes[:n] if m.get("id") and m.get("url")]


def templates(project, q: str | None = None, gif: bool = False, n: int = 12) -> list[dict]:
    project = ensure_project(project)
    res = template_search(q, gif, n)
    out = project / "assets" / "_candidates" / f"meme-{slugify(q or 'top')}.json"
    save_json(out, {"query": q or "", "kind": "meme", "results": res})
    log(f"{len(res)} templates -> {out}")
    for r in res:
        log(f"  {r['id']:<22} {r['title'][:44]:<44} {r.get('captions') or 0:>9,} captions  {r['width']}x{r['height']}  [UNVERIFIED]")
    if q and not res and not secret("IMGFLIP_API_KEY"):
        log("  nothing in the public top list. The full database (regional templates too) needs IMGFLIP_API_KEY, a paid Imgflip plan.")
    if res:
        log("download: fishvideo assets get <dir> <id>   (refused unless memes.policy is viral, or with --accept-risk)")
    return res


# ------------------------------------------------------------------ trending (research only)
def trending(project, region: str = "world", n: int = 10) -> Path:
    """What is being memed now: the most-captioned Imgflip templates and recent YouTube uploads for the region.
    Titles and links only. Nothing is downloaded, and none of it is licensed for reuse."""
    project = ensure_project(project)
    cfg = sources_cfg()
    if region not in cfg["regions"]:
        raise FishError(f"region must be one of {sorted(cfg['regions'])}")
    reg = cfg["regions"][region]
    lines = [f"# Meme trends: {reg['label']}", "", "Research only. Use it to pick a joke the audience knows; it grants no right to reuse anything listed.", ""]
    try:
        top = template_search(None, False, n)
        lines += ["## Most-captioned templates (Imgflip, worldwide)", "", "| Template | Captions | Page |", "|---|---|---|"]
        lines += [f"| {t['title']} | {t.get('captions') or 0:,} | {t['url']} |" for t in top]
    except fvnet.NetError as e:
        warn(f"imgflip: {e}")
    import youtube
    seen, vids = set(), []
    for q in reg.get("yt_queries") or []:
        try:
            for v in youtube.search(q, n=n, recent_days=14):
                if v.get("id") not in seen:
                    seen.add(v.get("id"))
                    vids.append(v)
        except FishError as e:
            warn(f"youtube '{q}': {e}")
    vids.sort(key=lambda v: -(v.get("views_per_day") or 0))
    if vids:
        lines += ["", f"## Recent uploads ({', '.join(reg.get('yt_queries') or [])})", "", "| Title | Views/day | Channel | Link |", "|---|---|---|---|"]
        lines += [f"| {str(v.get('title') or '').replace('|', '/')[:80]} | {int(v.get('views_per_day') or 0):,} | {str(v.get('channel') or '')[:30]} | {v.get('url')} |" for v in vids[:n]]
    lines += ["", "## Where to get them", ""]
    lines += [f"- {s['name']} ({s['access']}): {s['url']}" for s in sources(region)]
    out = project / "research" / "memes.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"meme trends for {reg['label']}: {len(vids[:n])} uploads -> {out}")
    return out


# ------------------------------------------------------------------ public-domain and CC film
def films(project, q: str, region: str | None = None, before: int | None = None, n: int = 12, unverified: bool | None = None) -> list[dict]:
    """Film on Wikimedia Commons and the Internet Archive. `before` keeps works from before that year
    (1931 is a common public-domain line in the US; check the country you publish in)."""
    import assets
    opts = {}
    if before:
        opts["before"] = int(before)
    if region:
        cfg = sources_cfg()
        if region not in cfg["regions"]:
            raise FishError(f"region must be one of {sorted(cfg['regions'])}")
        if cfg["regions"][region].get("archive_lang"):
            opts["lang"] = cfg["regions"][region]["archive_lang"]
    return assets.search(project, q, "video", ["wikimedia", "archive"], n, unverified, **opts)


# ------------------------------------------------------------------ add your own (or a clip a source handed you)
def add(project, src: str, title: str, source: str | None = None, source_url: str | None = None, license: str | None = None,
        author: str | None = None, name: str | None = None, accept_risk: bool = False, kind: str = "meme") -> Path:
    """Register an image or clip you brought (a file, or a media URL a source's own tool gave you) with its
    licence and risk tier, so QA and the credits know about it."""
    project = ensure_project(project)
    risk, lic, lurl, att = fvnet.claim_license(source, license)
    is_url = bool(re.match(r"https?://", str(src), re.I))
    ext = Path(urllib.parse.urlsplit(str(src)).path if is_url else str(src)).suffix.lower()
    allowed = IMAGE_EXT + VIDEO_EXT
    if ext not in allowed:
        raise FishError(f"a meme must be an image or a video ({', '.join(allowed)}); for a sound use `sounds add`")
    ident = fvnet.safe_name(name or slugify(title) or "meme")
    rec = {"id": f"{fvnet.safe_name(source or 'own')}-{ident}", "provider": source or "own", "kind": kind, "title": title[:140], "url": source_url or (src if is_url else ""),
           "author": author or "unknown", "license": lic, "license_url": lurl, "attribution_required": att, "risk": risk}
    fvnet.check_risk(project, rec, accept_risk)
    dest = project / "assets" / "meme" / f"{ident}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if is_url:
        fvnet.download_file(src, dest, timeout=120, max_bytes=200 << 20, types=("image/", "video/", "application/octet-stream", "binary/octet-stream"))
    else:
        if not Path(src).is_file():
            raise FishError(f"missing file: {src}")
        if Path(src).resolve() != dest.resolve():
            shutil.copyfile(src, dest)
    rec["file"] = str(dest.relative_to(project)).replace("\\", "/")
    add_credit(project, rec)
    log(f"added {rec['file']}  [{lic}; risk: {risk}]")
    return dest


# ------------------------------------------------------------------ contact sheet with timestamps
def sheet(video, out=None, every: float = 2.0, start: float = 0.0, end: float | None = None, cols: int = 6, width: int = 320) -> Path:
    """A grid of frames, one every `every` seconds, each labelled with its time, to pick the exact seconds of a gag.
    The labels are drawn with Pillow: the bundled ffmpeg has no text filter."""
    from PIL import Image, ImageDraw, ImageFont
    video = Path(video)
    if not video.is_file():
        raise FishError(f"missing file: {video}")
    if every <= 0 or cols < 1:
        raise FishError("--every must be above 0 and --cols at least 1")
    out = Path(out) if out else video.with_name(video.stem + "-sheet.png")
    tmp = Path(tempfile.mkdtemp(prefix="fv-sheet-"))
    try:
        cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start)]
        if end is not None:
            cmd += ["-t", str(max(0.1, end - start))]
        cmd += ["-protocol_whitelist", "file,pipe", "-i", str(video), "-an", "-vf", f"fps=1/{every:.4f},scale={int(width)}:-2", "-frames:v", "240", "-q:v", "4", str(tmp / "f_%04d.jpg")]
        run(cmd)
        frames = sorted(tmp.glob("f_*.jpg"))
        if not frames:
            raise FishError("ffmpeg produced no frames (check --from / --to)")
        with Image.open(frames[0]) as im:
            w, h = im.size
        rows = -(-len(frames) // cols)
        canvas = Image.new("RGB", (cols * w, rows * h), "#111111")
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.load_default(size=max(12, w // 16))
        except TypeError:               # Pillow before 10.1 has only the small bitmap font
            font = ImageFont.load_default()
        for i, f in enumerate(frames):
            x, y = (i % cols) * w, (i // cols) * h
            with Image.open(f) as im:
                canvas.paste(im, (x, y))
            t = start + i * every
            label = f"{int(t // 60)}:{t % 60:04.1f}"
            box = draw.textbbox((x + 5, y + 4), label, font=font)
            draw.rectangle((box[0] - 4, box[1] - 3, box[2] + 4, box[3] + 3), fill="#000000")
            draw.text((x + 5, y + 4), label, fill="#ffe24a", font=font)
        out.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    log(f"{len(frames)} frames, one every {every:g} s from {mmss(start)} -> {out}")
    return out


# ------------------------------------------------------------------ cut a moment
def _ledger_for(project: Path, src: Path) -> dict | None:
    try:
        rel = str(src.resolve().relative_to(project.resolve())).replace("\\", "/")
    except ValueError:
        return None
    return next((r for r in fvnet.load_credits(project) if r.get("file") == rel), None)


def cut(project, video, clip_id: str, start: float = 0.0, dur: float | None = None, aspect: str | None = None, focus=None, grade: str | None = None,
        sharpen: bool = False, width: int = 1920, fps: int = 30, title: str | None = None, source: str | None = None, source_url: str | None = None,
        license: str | None = None, author: str | None = None, accept_risk: bool = False) -> dict:
    """Cut a moment into build/clips/<clip_id> for the `meme` and `footage` scenes: pictures only (the sound is dropped),
    cropped to the frame's shape, with the source's licence carried over to the clip."""
    import assets
    project = ensure_project(project)
    video = Path(video)
    src = _ledger_for(project, video)
    if src:
        rec = {k: src.get(k) for k in ("provider", "title", "url", "author", "license", "license_url", "attribution_required", "risk")}
        rec["source_credit"] = src.get("id")
    else:
        risk, lic, lurl, att = fvnet.claim_license(source, license)
        rec = {"provider": source or "own", "title": (title or video.stem)[:140], "url": source_url or "", "author": author or "unknown",
               "license": lic, "license_url": lurl, "attribution_required": att, "risk": risk}
    rec.update(id=f"clip-{clip_id}", kind="clip")
    fvnet.check_risk(project, rec, accept_risk)
    meta = assets.prep_clip(project, video, clip_id, start, dur, fps, width, grade, sharpen, None, aspect, focus)
    rec["file"] = f"build/clips/{clip_id}"
    rec["cut"] = {"start": start, "dur": dur, "aspect": aspect}
    add_credit(project, rec)
    meta.update(credit=rec["id"], risk=fvnet.risk_of(rec), audio="dropped")
    save_json(project / "build" / "clips" / clip_id / "meta.json", meta)
    log(f"clip {clip_id}: {meta['frames']} frames, sound dropped  [{rec['license']}; risk: {meta['risk']}]")
    return meta


# ------------------------------------------------------------------ caption an image
def caption(image, out, top: str = "", bottom: str = "", width: int = 1080) -> Path:
    """Top and bottom meme captions on an image, drawn in the browser so any script (Devanagari too) is shaped correctly."""
    image, out = Path(image), Path(out)
    if not image.is_file():
        raise FishError(f"missing file: {image}")
    if image.suffix.lower() not in IMAGE_EXT:
        raise FishError(f"caption works on an image ({', '.join(IMAGE_EXT)})")
    if not (top or bottom):
        raise FishError("give --top, --bottom or both")
    out.parent.mkdir(parents=True, exist_ok=True)
    node("memecap.mjs", image.resolve(), out.resolve(), "--top", top or "", "--bottom", bottom or "", "--width", int(width), capture=True)
    if not out.exists():
        raise FishError("the caption render produced no file")
    log(f"captioned -> {out}")
    return out


# ------------------------------------------------------------------ lint
def _sticker_findings(project: Path, scenes: list) -> list[dict]:
    """Meme stickers inside newsstory scenes (fx kind meme) follow the same rules as meme scenes:
    the file exists, it has a credit record, the brief allows memes, and no gag repeats."""
    stickers = [(s.get("id"), f) for s in scenes if s.get("type") == "newsstory"
                for f in ((s.get("params") or {}).get("fx") or []) if f.get("kind") == "meme"]
    out: list[dict] = []
    if not stickers:
        return out
    if fvnet.memes_policy(project) == "none":
        out.append({"level": "WARN", "scene": stickers[0][0], "msg": "the brief says no memes (memes.policy: none), but newsstory scenes carry meme stickers"})
    files = {r.get("file") for r in fvnet.load_credits(project)}
    seen: dict[str, str] = {}
    for sid, f in stickers:
        key = str(f.get("src") or "").lstrip("./")
        if not key:
            out.append({"level": "FAIL", "scene": sid, "msg": "a meme sticker needs `src`"})
            continue
        if not (project / key).exists():
            out.append({"level": "FAIL", "scene": sid, "msg": f"meme sticker '{key}' is missing"})
        elif key not in files:
            out.append({"level": "FAIL", "scene": sid, "msg": f"meme sticker '{key}' has no credit record: register it with `memes add` or fetch it with `assets get`"})
        if key in seen and seen[key] != sid:
            out.append({"level": "WARN", "scene": sid, "msg": f"the same meme sticker as scene '{seen[key]}': pick a different reaction for this beat"})
        seen.setdefault(key, sid)
    return out


def lint(project) -> list[dict]:
    """Findings about the memes in a storyboard: [{level: FAIL|WARN, scene, msg}].

    FAIL  a `meme` scene whose picture or clip has no credit record, or whose file is missing
    WARN  the brief says no memes; a gag used twice; the same sound on three memes running; memes packed too close
          or, in a long video, missing for a long stretch"""
    project = ensure_project(project)
    sb = load_yaml(project / "storyboard.yaml") if (project / "storyboard.yaml").exists() else {}
    scenes = sb.get("scenes") or []
    memes = [(i, s) for i, s in enumerate(scenes) if s.get("type") == "meme"]
    out: list[dict] = _sticker_findings(project, scenes)
    if not memes:
        return out
    if fvnet.memes_policy(project) == "none":
        out.append({"level": "WARN", "scene": memes[0][1].get("id"), "msg": "the brief says no memes (memes.policy: none), but the storyboard has meme scenes"})
    files = {r.get("file") for r in fvnet.load_credits(project)}
    seen: dict[str, str] = {}
    sounds: list[str] = []
    for _, s in memes:
        p = s.get("params") or {}
        sid = s.get("id")
        key = None
        if p.get("clip"):
            key = f"build/clips/{p['clip']}"
            mj = project / "build" / "clips" / str(p["clip"]) / "meta.json"
            if not mj.exists():
                out.append({"level": "FAIL", "scene": sid, "msg": f"clip '{p['clip']}' is missing: cut it with `memes cut`"})
            elif key not in files:
                out.append({"level": "FAIL", "scene": sid, "msg": f"clip '{p['clip']}' has no credit record: cut it with `memes cut`, which carries the licence over"})
        elif p.get("src"):
            key = str(p["src"]).lstrip("./")
            if not (project / key).exists():
                out.append({"level": "FAIL", "scene": sid, "msg": f"picture '{key}' is missing"})
            elif key not in files:
                out.append({"level": "FAIL", "scene": sid, "msg": f"picture '{key}' has no credit record: register it with `memes add` or fetch it with `assets get`"})
        else:
            out.append({"level": "FAIL", "scene": sid, "msg": "a meme scene needs `src` (a picture) or `clip`"})
        if key:
            if key in seen:
                out.append({"level": "WARN", "scene": sid, "msg": f"the same gag as scene '{seen[key]}': a repeated meme reads as filler"})
            seen.setdefault(key, sid)
        sounds.append(str(p.get("sound") or ""))
    for k in range(2, len(sounds)):
        if sounds[k] and sounds[k] == sounds[k - 1] == sounds[k - 2]:
            out.append({"level": "WARN", "scene": memes[k][1].get("id"), "msg": f"the sound '{sounds[k]}' on three memes running: vary it"})
            break
    tl = next(iter(sorted((project / "build").glob("timeline-*.json"))), None) if (project / "build").exists() else None
    if tl:
        t = load_json(tl)
        at = {s["id"]: s["t0"] for s in t.get("scenes", [])}
        times = sorted(at[s.get("id")] for _, s in memes if s.get("id") in at)
        dur = float(t.get("duration") or 0)
        for a, b in zip(times, times[1:]):
            if b - a < 12:
                out.append({"level": "WARN", "scene": None, "msg": f"two memes {b - a:.0f} s apart (at {mmss(a)} and {mmss(b)}): a meme lands when it is a break, not a stream"})
                break
        if dur >= 180:
            gaps = [b - a for a, b in zip([0.0] + times, times + [dur])]
            if max(gaps) > 150:
                out.append({"level": "WARN", "scene": None, "msg": f"{max(gaps):.0f} s without a meme in a {mmss(dur)} video that uses them: about one a minute keeps the rhythm"})
    return out


# ------------------------------------------------------------------ CLI
def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="memes.py", description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("sources"); a.add_argument("--region")
    a = sp.add_parser("templates"); a.add_argument("project"); a.add_argument("q", nargs="?"); a.add_argument("--gif", action="store_true"); a.add_argument("-n", type=int, default=12)
    a = sp.add_parser("trending"); a.add_argument("project"); a.add_argument("--region", default="world"); a.add_argument("-n", type=int, default=10)
    a = sp.add_parser("films"); a.add_argument("project"); a.add_argument("q"); a.add_argument("--region"); a.add_argument("--before", type=int); a.add_argument("-n", type=int, default=12)
    a.add_argument("--unverified", action="store_true", help="also list items that state no licence (they stay gated)")
    a = sp.add_parser("add"); a.add_argument("project"); a.add_argument("src"); a.add_argument("--title", required=True); a.add_argument("--source"); a.add_argument("--source-url")
    a.add_argument("--license"); a.add_argument("--author"); a.add_argument("--id", dest="name"); a.add_argument("--accept-risk", action="store_true")
    a = sp.add_parser("sheet"); a.add_argument("video"); a.add_argument("--out"); a.add_argument("--every", type=float, default=2.0)
    a.add_argument("--from", dest="start", type=float, default=0.0); a.add_argument("--to", dest="end", type=float); a.add_argument("--cols", type=int, default=6); a.add_argument("--width", type=int, default=320)
    a = sp.add_parser("cut"); a.add_argument("project"); a.add_argument("video"); a.add_argument("clip_id"); a.add_argument("--start", type=float, default=0.0); a.add_argument("--dur", type=float)
    a.add_argument("--aspect"); a.add_argument("--focus"); a.add_argument("--grade"); a.add_argument("--sharpen", action="store_true"); a.add_argument("--width", type=int, default=1920)
    a.add_argument("--fps", type=int, default=30); a.add_argument("--title"); a.add_argument("--source"); a.add_argument("--source-url"); a.add_argument("--license"); a.add_argument("--author")
    a.add_argument("--accept-risk", action="store_true")
    a = sp.add_parser("caption"); a.add_argument("image"); a.add_argument("out"); a.add_argument("--top", default=""); a.add_argument("--bottom", default=""); a.add_argument("--width", type=int, default=1080)
    a = sp.add_parser("lint"); a.add_argument("project")
    ns = ap.parse_args(argv)
    if ns.cmd == "sources":
        print_sources(ns.region)
    elif ns.cmd == "templates":
        templates(ns.project, ns.q, ns.gif, ns.n)
    elif ns.cmd == "trending":
        trending(ns.project, ns.region, ns.n)
    elif ns.cmd == "films":
        films(ns.project, ns.q, ns.region, ns.before, ns.n, True if ns.unverified else None)
    elif ns.cmd == "add":
        add(ns.project, ns.src, ns.title, ns.source, ns.source_url, ns.license, ns.author, ns.name, ns.accept_risk)
    elif ns.cmd == "sheet":
        sheet(ns.video, ns.out, ns.every, ns.start, ns.end, ns.cols, ns.width)
    elif ns.cmd == "cut":
        focus = tuple(float(v) for v in ns.focus.split(",")) if ns.focus else None
        cut(ns.project, ns.video, ns.clip_id, ns.start, ns.dur, ns.aspect, focus, ns.grade, ns.sharpen, ns.width, ns.fps, ns.title, ns.source, ns.source_url,
            ns.license, ns.author, ns.accept_risk)
    elif ns.cmd == "caption":
        caption(ns.image, ns.out, ns.top, ns.bottom, ns.width)
    elif ns.cmd == "lint":
        found = lint(ns.project)
        for f in found:
            log(f"  {f['level']:<4}  {f['scene'] or '-':<14} {f['msg']}")
        log(f"meme lint: {len(found)} finding(s)")
        return 1 if any(f["level"] == "FAIL" for f in found) else 0
    return 0


if __name__ == "__main__":
    main_guard(cli)
