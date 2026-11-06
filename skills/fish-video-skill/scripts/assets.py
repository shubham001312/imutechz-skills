"""Asset search, download, licensing and processing.

    python scripts/assets.py search <project> "brain" --kind photo|video|audio|sfx|music [--providers pexels,openverse] [-n 12]
    python scripts/assets.py get <project> <candidate-id> [<candidate-id> ...] [--accept-risk]
    python scripts/assets.py shot <project> <url> [<url> ...] [--full] [--width 1440] [--dpr 2]
    python scripts/assets.py logo <project> <brand> [--color brand|white|black|#hex]
    python scripts/assets.py icon <project> <query | set:name> [--color #hex]
    python scripts/assets.py emoji <project> <emoji | UNICODE NAME> [--set openmoji|twemoji]
    python scripts/assets.py cutout <src.png> <dst.png> [--model isnet-general-use]
    python scripts/assets.py clip <project> <src.mp4> <clip_id> [--start 0] [--dur 6] [--fps 30] [--width 1080]
    python scripts/assets.py sfx-pack [dest]
    python scripts/assets.py credits <project>

Providers: pexels (photo/video, PEXELS_API_KEY), pixabay (photo/video,
PIXABAY_API_KEY), openverse (photo/audio, key-less, cc0/pdm/by/by-sa only),
wikimedia (photo/video/audio, key-less, CC0/PD/CC-BY/CC-BY-SA only), nasa
(photo/video, key-less), freesound (sfx, FREESOUND_API_KEY, CC0 only, hq-mp3
previews), archive (video/audio, Internet Archive, key-less; items with no
licence are `unverified` and hidden unless asked for).

Unified record: id, provider, kind, title, url, download_url, preview_url,
width, height, duration, author, author_url, license, license_url,
attribution_required, risk (safe | platform | unverified; see fvnet). `get`
refuses an unverified asset unless the project opted in. `search` writes assets/_candidates/<kind>-<slug>.json
plus small preview images; `get` downloads full files into
assets/<kind>/<provider>-<id>.<ext> and logs assets/credits.json.
"""
from __future__ import annotations

import argparse
import html
import io
import json
import re
import shutil
import urllib.parse
import zipfile
from pathlib import Path

from fvcore import SKILL, FishError, ensure_project, ffmpeg_bin, load_yaml, log, main_guard, run, save_json, save_yaml, secret, slugify, warn, load_json
import fvnet
from fvnet import add_credit, credits_path, credits_text, load_credits, norm_license

KINDS = ("photo", "video", "audio", "sfx", "music")
DEFAULT_PROVIDERS = {
    "photo": ["pexels", "pixabay", "openverse", "wikimedia", "nasa", "loc"],
    "video": ["pexels", "pixabay", "nasa", "wikimedia", "archive"],
    "audio": ["openverse", "wikimedia", "archive"],
    "music": ["openverse"],
    "sfx": ["freesound", "openverse", "wikimedia"],
}
# download caps per kind (bytes) and the content types a download may have
MAX_BYTES = {"photo": 40 << 20, "meme": 40 << 20, "icon": 1 << 20, "video": 400 << 20, "audio": 80 << 20, "music": 80 << 20, "sfx": 40 << 20}
_BIN = ("application/ogg", "application/octet-stream", "binary/octet-stream")
CTYPES = {"photo": ("image/",) + _BIN, "meme": ("image/", "video/") + _BIN, "icon": ("image/",) + _BIN, "video": ("video/",) + _BIN,
          "audio": ("audio/",) + _BIN, "music": ("audio/",) + _BIN, "sfx": ("audio/",) + _BIN}
REMBG_MODELS = ("isnet-general-use", "birefnet-general-lite", "birefnet-general", "u2net", "u2netp", "silueta", "isnet-anime", "birefnet-portrait")
KEY_NAMES = {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY", "freesound": "FREESOUND_API_KEY"}


def _rec(provider, pid, kind, title, url, download_url, preview_url, width=None, height=None, duration=None, author="", author_url="",
         lic="", lic_url="", attribution=None, risk=None, **extra) -> dict:
    n = norm_license(lic, lic_url)
    ok = n["ok"] or attribution is False
    if risk is None:
        risk = "safe" if ok else "unverified"
    r = {"id": f"{provider}-{fvnet.safe_name(pid)}", "provider": provider, "kind": kind, "title": (title or "").strip()[:140], "url": url,
         "download_url": download_url, "preview_url": preview_url, "width": width, "height": height, "duration": duration,
         "author": author or "", "author_url": author_url or "", "license": n["label"] if n["ok"] else lic, "license_url": n["url"] or lic_url,
         "attribution_required": n["attribution"] if attribution is None else attribution, "risk": risk, "_ok": ok}
    r.update(extra)
    return r


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


# ------------------------------------------------------------------ providers
def _pexels(q, kind, n):
    key = secret("PEXELS_API_KEY")
    if not key:
        raise FishError("PEXELS_API_KEY not set")
    H = {"Authorization": key}
    out = []
    if kind == "photo":
        for p in fvnet.fetch_json("https://api.pexels.com/v1/search", {"query": q, "per_page": n}, H).get("photos", []):
            s = p.get("src", {})
            out.append(_rec("pexels", p["id"], "photo", p.get("alt") or q, p["url"], s.get("original") or s.get("large2x"), s.get("medium"),
                            p.get("width"), p.get("height"), None, p.get("photographer"), p.get("photographer_url"), "Pexels License", "https://www.pexels.com/license/", attribution=False))
    else:
        for v in fvnet.fetch_json("https://api.pexels.com/v1/videos/search", {"query": q, "per_page": n}, H).get("videos", []):
            files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")]
            files.sort(key=lambda f: (abs(f["width"] - 1920) if f["width"] >= 1280 else 5000 - f["width"]))
            f = files[0] if files else {}
            out.append(_rec("pexels", v["id"], "video", q, v["url"], f.get("link"), v.get("image"), f.get("width") or v.get("width"), f.get("height") or v.get("height"),
                            v.get("duration"), (v.get("user") or {}).get("name"), (v.get("user") or {}).get("url"), "Pexels License", "https://www.pexels.com/license/", attribution=False))
    return out


def _pixabay(q, kind, n):
    key = secret("PIXABAY_API_KEY")
    if not key:
        raise FishError("PIXABAY_API_KEY not set")
    out = []
    lic, lurl = "Pixabay Content License", "https://pixabay.com/service/license-summary/"
    if kind == "photo":
        for h in fvnet.fetch_json("https://pixabay.com/api/", {"key": key, "q": q, "per_page": max(n, 3), "safesearch": "true"}).get("hits", [])[:n]:
            out.append(_rec("pixabay", h["id"], "photo", h.get("tags") or q, h.get("pageURL"), h.get("largeImageURL") or h.get("webformatURL"), h.get("webformatURL") or h.get("previewURL"),
                            h.get("imageWidth"), h.get("imageHeight"), None, h.get("user"), f"https://pixabay.com/users/{h.get('user')}-{h.get('user_id')}/", lic, lurl, attribution=False))
    else:
        for h in fvnet.fetch_json("https://pixabay.com/api/videos/", {"key": key, "q": q, "per_page": max(n, 3), "safesearch": "true"}).get("hits", [])[:n]:
            vs = h.get("videos", {})
            v = vs.get("large") if vs.get("large", {}).get("url") else vs.get("medium", {})
            prev = f"https://i.vimeocdn.com/video/{h['picture_id']}_640x360.jpg" if h.get("picture_id") else None
            out.append(_rec("pixabay", h["id"], "video", h.get("tags") or q, h.get("pageURL"), v.get("url"), prev, v.get("width"), v.get("height"), h.get("duration"),
                            h.get("user"), f"https://pixabay.com/users/{h.get('user')}-{h.get('user_id')}/", lic, lurl, attribution=False))
    return out


def _openverse(q, kind, n):
    audio = kind in ("audio", "music", "sfx")
    ep = "audio" if audio else "images"
    # anonymous requests may ask for at most 20 results: more is answered with HTTP 401
    args = {"q": q, "page_size": min(n * 2, 20), "license": "cc0,pdm,by,by-sa", "category": "sound_effect" if kind == "sfx" else None}
    d = fvnet.fetch_json(f"https://api.openverse.org/v1/{ep}/", args)
    short_only = False
    if kind == "sfx" and not d.get("results"):
        # few sounds carry the sound_effect category: search all audio and keep the short ones
        d = fvnet.fetch_json(f"https://api.openverse.org/v1/{ep}/", dict(args, category=None))
        short_only = True
    out = []
    for r in d.get("results", []):
        if short_only and (r.get("duration") or 0) > 30000:
            continue
        lic = (r.get("license") or "").lower()
        if lic not in ("cc0", "pdm", "by", "by-sa"):
            continue
        label = {"cc0": "CC0", "pdm": "Public Domain", "by": f"CC BY {r.get('license_version') or '4.0'}", "by-sa": f"CC BY-SA {r.get('license_version') or '4.0'}"}[lic]
        dur = (r.get("duration") or 0) / 1000 if audio else None
        out.append(_rec("openverse", r["id"], kind, r.get("title") or q, r.get("foreign_landing_url") or r.get("url"), r.get("url"), r.get("thumbnail") or (r.get("url") if not audio else None),
                        r.get("width"), r.get("height"), dur, r.get("creator"), r.get("creator_url"), label, r.get("license_url") or "", filetype=r.get("filetype")))
        if len(out) >= n:
            break
    return out


def _wikimedia(q, kind, n, **opts):
    """Wikimedia Commons. Photos, and with filetype search also video and audio (a small transcode is preferred for big films)."""
    av = kind != "photo"
    want = "VIDEO" if kind == "video" else "AUDIO"
    d = fvnet.fetch_json("https://commons.wikimedia.org/w/api.php", {
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": min(n * 2, 30),
        "gsrsearch": f"{q} filetype:{'video' if kind == 'video' else 'audio'}" if av else q,
        "prop": "videoinfo" if av else "imageinfo", ("viprop" if av else "iiprop"): "url|extmetadata|size|mime|mediatype" + ("|derivatives" if av else ""),
        **({} if av else {"iiurlwidth": 640})})
    out = []
    for pg in sorted((d.get("query", {}).get("pages") or {}).values(), key=lambda p: p.get("index", 0)):
        ii = ((pg.get("videoinfo") if av else pg.get("imageinfo")) or [{}])[0]
        mime = ii.get("mime", "")
        if av:
            if ii.get("mediatype") != want or "midi" in mime.lower():
                continue
        elif not (mime.startswith("image/") and mime not in ("image/svg+xml", "image/tiff")):
            continue
        md = ii.get("extmetadata", {})
        short = (md.get("LicenseShortName") or {}).get("value", "")
        lurl = (md.get("LicenseUrl") or {}).get("value", "")
        if not short:
            continue
        nl = norm_license(short, lurl)
        if not nl["ok"]:
            continue
        year = _year((md.get("DateTimeOriginal") or {}).get("value", ""))
        if opts.get("before") and not (year and year < int(opts["before"])):
            continue
        url, extra = ii.get("url"), {}
        if kind == "video":
            # the original can be hundreds of MB: take the largest WebM transcode up to 720p when there is one
            ders = [x for x in ii.get("derivatives") or [] if "webm" in str(x.get("type")) and (x.get("height") or 0) <= 720]
            if ders and (ii.get("size") or 0) > (60 << 20):
                url = max(ders, key=lambda x: x.get("height") or 0)["src"]
            extra = {"year": year}
        out.append(_rec("wikimedia", pg["pageid"], kind, _strip((md.get("ObjectName") or {}).get("value", "")) or pg["title"].replace("File:", ""),
                        ii.get("descriptionurl"), url, ii.get("thumburl"), ii.get("width"), ii.get("height"), ii.get("duration") if av else None,
                        _strip((md.get("Artist") or {}).get("value", "")), "", short, lurl, **extra))
        if len(out) >= n:
            break
    return out


def _year(text: str) -> int | None:
    m = re.search(r"(1[89]\d\d|20\d\d)", _strip(text))
    return int(m.group(1)) if m else None


def _archive(q, kind, n, **opts):
    """Internet Archive. Items that state a licence are kept as usual; items with none are `unverified`."""
    mt = "movies" if kind == "video" else "audio"
    query = f"({q}) AND mediatype:{mt}"
    if opts.get("before"):
        query += f" AND year:[1880 TO {int(opts['before']) - 1}]"
    if opts.get("lang"):
        query += f" AND language:({opts['lang']})"
    d = fvnet.fetch_json("https://archive.org/advancedsearch.php", {"q": query, "fl[]": ["identifier", "title", "year", "licenseurl", "creator", "downloads"],
                                                                    "sort[]": "downloads desc", "rows": min(n * 2, 50), "output": "json"})
    out = []
    for it in d.get("response", {}).get("docs", []):
        ident = str(it.get("identifier") or "")
        if not ident:
            continue
        lurl = str(it.get("licenseurl") or "")
        creator = it.get("creator")
        sl = fvnet.strict_license_url(lurl)    # the link is the uploader's own text: only a real creativecommons.org licence page counts
        if sl["restricted"]:
            continue            # states an NC / ND licence
        rec = _rec("archive", ident, kind, it.get("title") or ident, f"https://archive.org/details/{urllib.parse.quote(ident)}", None, None, None, None, None,
                   ", ".join(creator) if isinstance(creator, list) else creator or "", "", sl["label"] if sl["ok"] else "no verifiable licence" + (" (the uploader's link is not a Creative Commons page)" if lurl else ""),
                   sl["url"] if sl["ok"] else "", risk="safe" if sl["ok"] else "unverified", year=_year(str(it.get("year") or "")), identifier=ident)
        rec["_ok"] = True
        out.append(rec)
        if len(out) >= n:
            break
    return out


def _archive_resolve(r: dict) -> str | None:
    """The smallest web-friendly file of an Internet Archive item."""
    ident = r.get("identifier") or r["id"].split("-", 1)[1]
    files = fvnet.fetch_json(f"https://archive.org/metadata/{urllib.parse.quote(ident)}").get("files") or []
    if r["kind"] == "video":
        order = [("h.264", ".mp4"), ("512kb mpeg4", ".mp4"), ("mpeg4", ".mp4"), ("ogg video", ".ogv")]
    else:
        order = [("vbr mp3", ".mp3"), ("mp3", ".mp3"), ("ogg vorbis", ".ogg"), ("flac", ".flac"), ("wave", ".wav")]
    for fmt, ext in order:
        hit = sorted((f for f in files if fmt in str(f.get("format", "")).lower() and str(f.get("name", "")).lower().endswith(ext)), key=lambda f: int(f.get("size") or 0))
        if hit:
            return f"https://archive.org/download/{urllib.parse.quote(ident)}/{urllib.parse.quote(hit[0]['name'])}"
    return None


def _nasa(q, kind, n):
    d = fvnet.fetch_json("https://images-api.nasa.gov/search", {"q": q, "media_type": "video" if kind == "video" else "image", "page_size": n})
    out = []
    for it in d.get("collection", {}).get("items", [])[:n]:
        dd = (it.get("data") or [{}])[0]
        prev = next((l["href"] for l in it.get("links", []) if l.get("rel") == "preview"), None)
        out.append(_rec("nasa", dd.get("nasa_id", "").replace("/", "_"), kind, dd.get("title") or q, f"https://images.nasa.gov/details/{urllib.parse.quote(dd.get('nasa_id', ''))}",
                        None, prev, None, None, None, dd.get("photographer") or dd.get("secondary_creator") or dd.get("center") or "NASA", "",
                        "NASA media (public domain; no endorsement implied)", "https://www.nasa.gov/nasa-brand-center/images-and-media/", attribution=False,
                        collection_url=it.get("href")))
    return out


def _freesound(q, kind, n):
    key = secret("FREESOUND_API_KEY")
    if not key:
        raise FishError("FREESOUND_API_KEY not set")
    d = fvnet.fetch_json("https://freesound.org/apiv2/search/text/", {"query": q, "filter": 'license:"Creative Commons 0"', "page_size": n, "token": key,
                                                                    "fields": "id,name,previews,license,username,duration,url"})
    out = []
    for s in d.get("results", []):
        pv = s.get("previews") or {}
        out.append(_rec("freesound", s["id"], "sfx", s.get("name") or q, s.get("url") or f"https://freesound.org/s/{s['id']}/", pv.get("preview-hq-mp3"), pv.get("preview-lq-mp3"),
                        None, None, s.get("duration"), s.get("username"), f"https://freesound.org/people/{s.get('username')}/", "CC0", "https://creativecommons.org/publicdomain/zero/1.0/"))
    return out


def _loc(q, kind, n):
    """Library of Congress Prints & Photographs (loc.gov JSON API). Only items whose rights statement says no known restrictions or public domain are 'safe'."""
    d = fvnet.fetch_json("https://www.loc.gov/photos/", {"q": q, "fo": "json", "c": n})
    out = []
    for it in (d.get("results") or [])[:n]:
        imgs = it.get("image_url") or []
        if not imgs:
            continue
        rights = " ".join(str(x) for x in ([it.get("rights_advisory"), it.get("rights")] if not isinstance(it.get("rights"), list) else [it.get("rights_advisory")] + it["rights"]) if x).lower()
        ok = "no known restrictions" in rights or "public domain" in rights
        who = it.get("contributor") or it.get("creator") or []
        who = who[0] if isinstance(who, list) and who else (who if isinstance(who, str) else "")
        out.append(_rec("loc", str(it.get("id") or it.get("url") or "").rstrip("/").split("/")[-1], kind, it.get("title") or q, it.get("url") or it.get("id") or "",
                        imgs[-1], imgs[0], None, None, None, who or "Library of Congress, Prints and Photographs Division", "",
                        "Library of Congress: no known restrictions" if ok else (rights[:80] or ""), "https://www.loc.gov/rr/print/res/", attribution=False if ok else None,
                        risk="safe" if ok else "unverified"))
    return out


PROVIDERS = {"pexels": (_pexels, ("photo", "video")), "pixabay": (_pixabay, ("photo", "video")), "openverse": (_openverse, ("photo", "audio", "music", "sfx")),
             "wikimedia": (_wikimedia, ("photo", "video", "audio", "music", "sfx")), "nasa": (_nasa, ("photo", "video")), "loc": (_loc, ("photo",)), "freesound": (_freesound, ("sfx",)),
             "archive": (_archive, ("video", "audio", "music", "sfx"))}
TAKES_OPTS = {"wikimedia", "archive"}       # providers that understand before= (a year) and lang=


MAX_PHOTO_SIDE = 2400      # a downloaded photo is kept at most this many px on its long side: the renderer decodes every picture, and a 47-megapixel original stalls the browser


def limit_size(path: Path, max_side: int = MAX_PHOTO_SIDE) -> tuple[int, int] | None:
    """Shrink a photo in place when its long side exceeds `max_side` (never enlarges). Returns the original size when it shrank."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
            if max(w, h) <= max_side:
                return None
            k = max_side / max(w, h)
            small = im.convert("RGB").resize((round(w * k), round(h * k)), Image.LANCZOS)
        small.save(path, quality=92)
        return (w, h)
    except Exception:                                              # noqa: BLE001 - an unreadable file is reported by the gate
        return None


# ------------------------------------------------------------------ search / get
def search_providers(q: str, kind: str, providers=None, n: int = 12, unverified: bool = False, **opts) -> list[dict]:
    """Query providers (no disk writes). Drops NC/ND/unknown licences. Soft-fails per provider.

    unverified=True also returns results that state no licence at all (risk `unverified`); `get` still gates them.
    opts (before=<year>, lang=<code>) go to the providers that understand them."""
    if kind not in KINDS:
        raise FishError(f"kind must be one of {', '.join(KINDS)}")
    res: list[dict] = []
    for name in providers or DEFAULT_PROVIDERS[kind]:
        if name not in PROVIDERS:
            warn(f"unknown provider '{name}'")
            continue
        fn, kinds = PROVIDERS[name]
        if kind not in kinds:
            continue
        try:
            got = fn(q, kind, n, **opts) if name in TAKES_OPTS else fn(q, kind, n)
        except fvnet.NetError as e:
            warn(f"{name}: {e}")
            continue
        except FishError as e:
            warn(f"{name} skipped: {e}" + (f" (key-less alternatives: {', '.join(p for p in DEFAULT_PROVIDERS[kind] if p not in KEY_NAMES)})" if name in KEY_NAMES else ""))
            continue
        except (KeyError, TypeError, ValueError) as e:
            warn(f"{name}: unexpected response ({e})")
            continue
        res += [r for r in got if r.get("_ok") and (unverified or fvnet.risk_of(r) != "unverified")]
    for r in res:
        r.pop("_ok", None)
    return res


def _ext(url: str, default: str) -> str:
    e = Path(urllib.parse.urlsplit(url or "").path).suffix.lower()
    return e if re.fullmatch(r"\.[a-z0-9]{2,4}", e or "") else default


def search(project, q: str, kind: str = "photo", providers=None, n: int = 12, unverified: bool | None = None, **opts) -> list[dict]:
    """Search, write assets/_candidates/<kind>-<slug>.json and download small previews next to it.

    unverified defaults to the project's choice: only a `memes.policy: viral` project sees results with no licence."""
    project = ensure_project(project)
    if unverified is None:
        unverified = fvnet.memes_policy(project) == "viral"
    res = search_providers(q, kind, providers, n, unverified, **opts)
    cdir = project / "assets" / "_candidates"
    cdir.mkdir(parents=True, exist_ok=True)
    for r in res:
        pu = r.get("preview_url")
        if not pu:
            continue
        dflt = ".mp3" if kind in ("audio", "sfx", "music") else ".jpg"
        dest = cdir / f"{r['id']}{_ext(pu, dflt)}"
        if kind in ("audio", "music") and r["provider"] == "openverse":
            continue  # audio previews are full tracks; skip bulky pre-download
        try:
            if not dest.exists():
                fvnet.download_file(pu, dest, timeout=20, max_bytes=20 << 20)
            r["preview_file"] = dest.name
        except fvnet.NetError as e:
            warn(f"preview skipped for {r['id']}: {e}")
    out = cdir / f"{kind}-{slugify(q)}.json"
    save_json(out, {"query": q, "kind": kind, "results": res})
    log(f"{len(res)} candidates -> {out}")
    for r in res:
        tag = "" if fvnet.risk_of(r) == "safe" else f"  [{fvnet.risk_of(r).upper()}]"
        log(f"  {r['id']:<28} {str(r['license'])[:14]:<14} {(r['title'] or '')[:50]}  by {r['author'][:24]}{tag}")
    return res


def _find_candidates(project: Path, ids: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for f in sorted((project / "assets" / "_candidates").glob("*.json")):
        try:
            for r in json.loads(f.read_text(encoding="utf-8")).get("results", []):
                if r["id"] in ids:
                    found[r["id"]] = r
        except (ValueError, OSError):
            continue
    return found


def _nasa_resolve(r: dict) -> str | None:
    items = fvnet.fetch_json(r["collection_url"]) if r.get("collection_url") else []
    if r["kind"] == "video":
        order = ["~medium.mp4", "~small.mp4", "~large.mp4", "~orig.mp4", ".mp4"]
    else:
        order = ["~large.jpg", "~medium.jpg", "~orig.jpg", ".jpg", ".png"]
    for suffix in order:
        for u in items:
            if u.lower().endswith(suffix):
                return u.replace("http://", "https://")
    return None


def get(project, candidate_ids, accept_risk: bool = False) -> list[Path]:
    """Download candidates fully into assets/<kind>/<provider>-<id>.<ext> and log credits (deduped).

    An asset whose licence is not verified is refused unless the project opted in (memes.policy: viral) or accept_risk is set."""
    project = ensure_project(project)
    ids = [candidate_ids] if isinstance(candidate_ids, str) else list(candidate_ids)
    cands = _find_candidates(project, ids)
    out: list[Path] = []
    for cid in ids:
        r = cands.get(cid)
        if not r:
            warn(f"{cid}: not in assets/_candidates (run `assets.py search` first)")
            continue
        try:
            fvnet.check_risk(project, r, accept_risk)
            url = r.get("download_url")
            if not url and r["provider"] == "nasa":
                url = _nasa_resolve(r)
            if not url and r["provider"] == "archive":
                url = _archive_resolve(r)
            if not url:
                raise FishError("no download URL")
            kind = fvnet.safe_name(r["kind"])
            dflt = {"photo": ".jpg", "meme": ".jpg", "icon": ".svg", "video": ".mp4"}.get(kind, ".mp3")
            if r["provider"] == "openverse" and r.get("filetype"):
                dflt = "." + fvnet.safe_name(str(r["filetype"]).lower(), 5)
            dest = project / "assets" / kind / f"{fvnet.safe_name(r['id'])}{_ext(url, dflt)}"
            if not dest.exists():
                fvnet.download_file(url, dest, timeout=120, max_bytes=MAX_BYTES.get(kind, 80 << 20), types=CTYPES.get(kind))
        except FishError as e:
            warn(f"{cid}: {e}")
            continue
        orig = limit_size(dest) if kind == "photo" else None
        rec = {k: v for k, v in r.items() if k not in ("preview_file", "collection_url", "filetype", "identifier")}
        if orig:
            rec["original_size"] = list(orig)
        rec["file"] = str(dest.relative_to(project)).replace("\\", "/")
        rec["credit"] = fvnet.credit_line(rec)
        added = add_credit(project, rec)
        log(f"{'got' if added else 'have'} {cid} -> {rec['file']}  [{r['license']}]")
        out.append(dest)
    return out


# ------------------------------------------------------------------ processing
def cutout(src, dst, model: str = "isnet-general-use") -> Path | None:
    """Background removal via rembg with an explicit permissive model (never the default bria model)."""
    if "bria" in model.lower():
        raise FishError("the bria model is non-commercial: use isnet-general-use or birefnet-general-lite")
    if model not in REMBG_MODELS:
        warn(f"model '{model}' not in the vetted list {REMBG_MODELS}; use at your own licence risk")
    try:
        from rembg import new_session, remove  # type: ignore
        from PIL import Image
    except ImportError:
        warn('rembg is not installed: pip install "rembg[cpu]"  (cutout skipped)')
        return None
    try:
        sess = new_session(model)
        img = Image.open(src).convert("RGBA")
        res = remove(img, session=sess)
        # trim to the visible object, so `w` in a scene means the object and not transparent padding
        box = res.getchannel("A").point(lambda a: 255 if a > 12 else 0).getbbox()
        if box:
            pad = int(max(res.size) * 0.01)
            res = res.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(res.width, box[2] + pad), min(res.height, box[3] + pad)))
        res.thumbnail((1600, 1600))
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        res.save(dst, optimize=True)
    except Exception as e:
        warn(f"cutout failed: {str(e)[:200]}")
        return None
    log(f"cutout ({model}) -> {dst}")
    return Path(dst)


GRADES = {
    "warm": "eq=saturation=1.08:contrast=1.04,colorbalance=rs=0.06:gs=0.01:bs=-0.07:rm=0.05:bm=-0.05:rh=0.04:bh=-0.05",
    "cool": "eq=saturation=1.03:contrast=1.04,colorbalance=rs=-0.05:bs=0.07:rm=-0.04:bm=0.05:rh=-0.03:bh=0.05",
    "teal-orange": "eq=saturation=1.12:contrast=1.08,colorbalance=rs=-0.08:gs=0.0:bs=0.10:rm=0.0:bm=0.0:rh=0.12:gh=0.03:bh=-0.10",
    "bw": "hue=s=0,curves=all='0/0 0.25/0.20 0.75/0.82 1/1'",
}


ASPECTS = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:5": 4 / 5}


def crop_filter(aspect: str, focus: tuple[float, float] | None = None) -> str:
    """An ffmpeg crop to an aspect ratio, as large as fits, centred on focus (fractions of the frame; default the centre)."""
    if aspect not in ASPECTS:
        raise FishError(f"unknown aspect '{aspect}': one of {sorted(ASPECTS)}")
    a = ASPECTS[aspect]
    fx, fy = (min(1.0, max(0.0, float(v))) for v in (focus or (0.5, 0.5)))
    w, h = f"min(iw\\,ih*{a:.6f})", f"min(ih\\,iw/{a:.6f})"
    return f"crop={w}:{h}:(iw-{w})*{fx:.4f}:(ih-{h})*{fy:.4f}"


def clip_filters(fps: int, width: int, grade: str | None = None, sharpen: bool = False, lut: str | Path | None = None,
                 aspect: str | None = None, focus: tuple[float, float] | None = None) -> str:
    """The ffmpeg -vf chain of prep_clip: [crop] -> [light denoise] -> fps -> scale -> [sharpen] -> [grade] -> [.cube LUT]."""
    if grade and grade not in GRADES:
        raise FishError(f"unknown grade '{grade}': one of {sorted(GRADES)}")
    parts = []
    if aspect:
        parts.append(crop_filter(aspect, focus))
    if sharpen:
        parts.append("hqdn3d=1.5:1.5:3:3")
    parts += [f"fps={fps}", f"scale='min({width},iw)':-2:flags=lanczos"]
    if sharpen:
        parts.append("unsharp=5:5:0.8")
    if grade:
        parts.append(GRADES[grade])
    if lut:
        lp = Path(lut)
        if not lp.exists() or lp.suffix.lower() != ".cube":
            raise FishError(f"LUT must be an existing .cube file: {lut}")
        # filter-graph escaping: forward slashes, escape the drive colon and quotes
        esc = lp.resolve().as_posix().replace(":", chr(92) + ":").replace("'", chr(92) + "'")
        parts.append(f"lut3d=file='{esc}'")
    return ",".join(parts)


def prep_clip(project, src, clip_id: str, start: float = 0, dur: float | None = None, fps: int = 30, width: int = 1080,
              grade: str | None = None, sharpen: bool = False, lut: str | Path | None = None,
              aspect: str | None = None, focus: tuple[float, float] | None = None) -> dict:
    """Extract frames to build/clips/<clip_id>/f_%05d.jpg + meta.json {frames,fps,W,H,src}.

    grade   warm | cool | teal-orange | bw  (ffmpeg eq/colorbalance/curves, no LUT files)
    sharpen light hqdn3d first, then lanczos scale + unsharp=5:5:0.8 (soft stock footage)
    lut     path to a .cube file, applied last with lut3d
    aspect  16:9 | 9:16 | 1:1 | 4:5: crop to that shape first (focus = the point to keep, fractions of the frame)
    The sound is always dropped: a clip is pictures only.
    """
    project = ensure_project(project)
    src = Path(src)
    if not src.exists():
        raise FishError(f"missing file: {src}")
    if fvnet.safe_name(clip_id) != clip_id:
        raise FishError(f"clip id '{clip_id}' must use only letters, digits, dot, dash and underscore")
    out = project / "build" / "clips" / clip_id
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start)]
    if dur:
        cmd += ["-t", str(dur)]
    cmd += ["-protocol_whitelist", "file,pipe", "-i", str(src), "-an", "-vf", clip_filters(fps, width, grade, sharpen, lut, aspect, focus), "-q:v", "3", str(out / "f_%05d.jpg")]
    run(cmd)
    frames = sorted(out.glob("f_*.jpg"))
    if not frames:
        raise FishError("ffmpeg produced no frames (check start/dur)")
    from PIL import Image
    with Image.open(frames[0]) as im:
        W, H = im.size
    meta = {"frames": len(frames), "fps": fps, "W": W, "H": H, "src": str(src)}
    if grade or sharpen or lut or aspect:
        meta["look"] = {k: v for k, v in {"grade": grade, "sharpen": sharpen or None, "lut": str(lut) if lut else None, "aspect": aspect}.items() if v}
    save_json(out / "meta.json", meta)
    log(f"{len(frames)} frames ({W}x{H} @ {fps}) -> {out}")
    return meta


# ------------------------------------------------------------------ website stills
def shot(project, urls, width: int = 1440, height: int = 900, dpr: float = 2, full: bool = False, wait: float = 2.5, keep_banners: bool = False, allow_private: bool = False) -> list[Path]:
    """Read-only stills of web pages into assets/shots/, with cookie banners hidden. Each one is logged as a
    `platform` asset: a screenshot shows someone else's site, under that site's terms."""
    project = ensure_project(project)
    urls = [fvnet.strip_userinfo(fvnet.http_only(u)) for u in ([urls] if isinstance(urls, str) else urls)]
    if not allow_private:
        for u in urls:
            if fvnet.private_host(urllib.parse.urlsplit(u).hostname):
                raise FishError(f"refused a local or private address: {u[:80]} (a page on your own machine or network: pass --allow-private if you mean it)")
    from fvcore import browser_bin, last_json_line, node
    if not browser_bin():
        raise FishError("a screenshot needs Chromium/Brave/Chrome: set BROWSER=/path")
    args = ["--width", width, "--height", height, "--dpr", dpr, "--wait", wait] + (["--full"] if full else []) + (["--keep-banners"] if keep_banners else []) + (["--allow-private"] if allow_private else [])
    r = node("shot.mjs", project, *urls, *args, capture=True)
    rep = last_json_line(r.stdout) or {}
    out = []
    for it in rep.get("shots", []):
        if it.get("error"):
            warn(f"{it['url']}: {it['error']}")
            continue
        rel = str(Path(it["file"]).resolve().relative_to(project.resolve())).replace("\\", "/")
        host = urllib.parse.urlsplit(it["url"]).hostname or ""
        title = re.sub(r"[\x00-\x1f\x7f]+", " ", str(it.get("title") or "")).strip()
        add_credit(project, {"id": f"screenshot-{Path(it['file']).stem}", "provider": "screenshot", "kind": "photo", "title": (title or host)[:140],
                             "url": it["url"], "author": host, "license": "Screenshot of a third-party website (no open licence)", "license_url": "",
                             "attribution_required": False, "risk": "platform", "file": rel, "hidden_banners": it.get("hidden", 0)})
        log(f"shot {it['url']} -> {rel}" + (f"  ({it['hidden']} banner element(s) hidden)" if it.get("hidden") else ""))
        out.append(Path(it["file"]))
    return out


# ------------------------------------------------------------------ Kenney SFX pack
KENNEY_PACKS = ["interface-sounds", "impact-sounds", "ui-audio"]
CUE_KEYWORDS = {
    "pop": ["pluck", "drop", "bong", "pop", "open", "question"],
    "tick": ["tick", "rollover", "scroll"],
    "click": ["click", "switch", "toggle", "select"],
    "swish": ["swish", "scratch", "minimize", "maximize", "slide"],
    "whoosh": ["whoosh", "swoosh", "maximize", "minimize", "slide"],
    "riser": ["riser", "rise", "sweep", "build"],
    "impact": ["impact"],
    "boom": ["boom", "heavy", "explosion"],
    "thump": ["thump", "soft", "wood", "punch"],
    "zap": ["zap", "laser", "electric", "error"],
    "coin": ["coin", "confirmation", "glass"],
    "paper": ["paper", "book", "cloth", "page"],
    "typing": ["type", "typing", "key"],
    "chime": ["chime", "bong", "confirmation", "glass", "bell"],
}
AUDIO_EXT = (".ogg", ".wav", ".mp3")


def build_sfx_index(lib: Path) -> dict:
    """Map our cue types to candidate files (paths relative to lib) by filename keywords."""
    packs = [d for d in lib.iterdir() if d.is_dir() and (d / "pack.json").exists()]  # committed packs carry their own index
    files = sorted(p for p in lib.rglob("*") if p.suffix.lower() in AUDIO_EXT and not any(d in p.parents for d in packs))
    idx: dict[str, list[str]] = {}
    for cue, kws in CUE_KEYWORDS.items():
        hit = []
        for kw in kws:
            hit += [str(p.relative_to(lib)).replace("\\", "/") for p in files if kw in p.stem.lower() and str(p.relative_to(lib)).replace("\\", "/") not in hit]
        idx[cue] = hit[:24]
    save_json(lib / "index.json", {"license": "CC0 (Kenney, kenney.nl)", "cues": idx, "count": len(files)})
    return idx


def _kenney_zip(slug: str) -> bytes:
    page = f"https://kenney.nl/assets/{slug}"
    did = ("assets/" + slug).encode().hex()
    d = fvnet.fetch_json(f"https://kenney.nl/download-link/{did}", headers={"Referer": page, "Accept": "application/json"})
    if not d.get("url"):
        raise fvnet.NetError(f"kenney gave no download link for {slug}")
    return fvnet.fetch(d["url"], headers={"Referer": page}, timeout=60)


def sfx_pack(dest=None) -> dict:
    """Download Kenney CC0 audio packs (UI + impacts) into <skill>/sfx/library/ and build index.json."""
    lib = Path(dest) if dest else SKILL / "sfx" / "library"
    lib.mkdir(parents=True, exist_ok=True)
    for slug in KENNEY_PACKS:
        if (lib / slug).exists() and any((lib / slug).rglob("*.ogg")):
            log(f"have {slug}")
            continue
        try:
            raw = _kenney_zip(slug)
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                lic = next((z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.lower().endswith("license.txt")), "")
                if "cc0" not in lic.lower() and "creative commons zero" not in lic.lower():
                    warn(f"{slug}: licence is not CC0, skipped")
                    continue
                for n in z.namelist():
                    if n.lower().endswith(AUDIO_EXT) or n.lower().endswith("license.txt"):
                        tgt = lib / slug / Path(n).name
                        tgt.parent.mkdir(parents=True, exist_ok=True)
                        tgt.write_bytes(z.read(n))
            log(f"downloaded {slug}")
        except (fvnet.NetError, zipfile.BadZipFile, FishError) as e:
            warn(f"{slug}: {e} (SFX pack incomplete; try again later or download from kenney.nl manually)")
    idx = build_sfx_index(lib)
    log("sfx index: " + ", ".join(f"{k}={len(v)}" for k, v in idx.items()))
    return idx


# ------------------------------------------------------------------ CLI
# ------------------------------------------------------------------ source: one command from beat to credited file
SOURCE_PROVIDERS = ("wikimedia", "nasa", "loc")           # keyless, licence confirmed by the API; stock keys are added when configured


def _beat_patch(project: Path, beat: str, rel: str, label: str) -> None:
    """Point a storyboard beat at the downloaded file: `src` when it has none, else append to `srcs`; set the honesty label."""
    sbf = Path(project) / "storyboard.yaml"
    sb = load_yaml(sbf)
    sc = next((s for s in sb.get("scenes", []) if s.get("id") == beat), None)
    if sc is None:
        raise FishError(f"no beat '{beat}' in storyboard.yaml (beats: {', '.join(str(s.get('id')) for s in sb.get('scenes', []))})")
    p = sc.setdefault("params", {})
    placeholder = lambda v: isinstance(v, str) and "TODO" in v                                  # noqa: E731
    if not p.get("src") or placeholder(p.get("src")):
        p["src"] = rel
    else:
        srcs = p.get("srcs") or [{"src": p["src"]}]
        if not any(x.get("src") == rel for x in srcs):
            srcs.append({"src": rel})
        p["srcs"] = srcs
    if sc.get("type") in ("story", "image", "statement"):
        p["label"] = label
    save_yaml(sbf, sb)


def _used_files(project: Path, except_beat: str | None) -> set[str]:
    sbf = Path(project) / "storyboard.yaml"
    out = set()
    if sbf.exists():
        for sc in load_yaml(sbf).get("scenes", []):
            if sc.get("id") == except_beat:
                continue
            p = sc.get("params") or {}
            for v in [p.get("src")] + [x.get("src") for x in (p.get("srcs") or []) if isinstance(x, dict)]:
                if isinstance(v, str):
                    out.add(Path(v).stem)
    return out


def source(project, query: str, beat: str | None = None, n: int = 1, providers=None, kind: str = "photo", depicts: str | None = None,
           before: int | None = None, min_width: int | None = None, min_height: int | None = None) -> list[dict]:
    """Search Commons, NASA, the Library of Congress (and Pexels/Pixabay when their keys are set), keep only results whose licence the API
    confirms, download the best `n`, write source, licence and author to assets/credits.json (so they reach every post text and the
    metadata), and point the beat at the file. `depicts` says the picture truly shows that person or event (label: archive photo);
    otherwise the beat is labelled `illustrative`. Returns the credit records."""
    project = ensure_project(project)
    prov = list(providers or SOURCE_PROVIDERS)
    if not providers:
        prov += [k for k in ("pexels", "pixabay") if secret(KEY_NAMES[k], project)]
    opts = {"before": before} if before else {}
    cands = search(project, query, kind, prov, max(n * 4, 8), False, **opts)
    safe = [c for c in cands if c.get("risk") == "safe" and c.get("_ok", True)]
    if not safe:
        raise FishError(f"no result for '{query}' has a licence the API confirms (providers: {', '.join(prov)}). Try other words, add --providers, or "
                        "make the beat a drawn graphic. Nothing is used with an unconfirmed licence.")
    if kind == "photo":
        import gates
        if min_width is None:
            from fvcore import project_config
            try:
                min_width = gates.min_native_width(gates.frame_size(project, None)[0])
            except Exception:                                         # noqa: BLE001 - no platform yet: a sane default
                min_width = 540
        if min_height is None:
            try:
                min_height = gates.min_native_height(gates.frame_size(project, None)[1])
            except Exception:                                         # noqa: BLE001
                min_height = 0
        big = [c for c in safe if (c.get("width") or 0) >= min_width and (c.get("height") or 10 ** 6) >= min_height]
        small = [c for c in safe if c.get("width") and ((c.get("width") or 0) < min_width or (c.get("height") or 10 ** 6) < min_height)]
        unknown = [c for c in safe if not c.get("width")]
        if big or unknown:                                           # sharp enough first, biggest first; undersized ones are dropped, not down-ranked into use
            safe = sorted(big, key=lambda c: -(c.get("width") or 0)) + unknown
            if small:
                warn(f"{len(small)} result(s) under {min_width}px wide were skipped: they would render muddy")
        else:
            raise FishError(f"every licence-confirmed result for '{query}' is too small (under {min_width}x{min_height}px; largest {max(c['width'] for c in small)}px): it would render blurry. Try other words or --min-width to accept smaller.")
    used = _used_files(project, beat)
    fresh = [c for c in safe if Path(c["id"]).stem not in used]
    if fresh or not used:
        safe = fresh or safe
    if not safe:
        raise FishError(f"no result for '{query}' has a licence the API confirms (providers: {', '.join(prov)}). Try other words, add --providers, or "
                        "make the beat a drawn graphic. Nothing is used with an unconfirmed licence.")
    files: list[Path] = []
    for c in safe:                                                   # a result whose download fails (too large, gone) is skipped for the next one
        if len(files) >= n:
            break
        files += get(project, [c["id"]])
    if not files:
        raise FishError(f"none of the {len(safe)} licence-confirmed results for '{query}' could be downloaded (too large or unavailable). Try other words or another provider.")
    idx = {r["file"]: r for r in load_credits(project)}
    out = []
    for f in files:
        rel = str(Path(f).relative_to(project)).replace("\\", "/")
        rec = idx.get(rel)
        if rec is None:
            continue
        if depicts:
            rec["depicts"] = depicts
            rec["depicts_verified"] = True
            save_json(credits_path(project), list(idx.values()))
        out.append(rec)
        if beat:
            _beat_patch(project, beat, rel, "archive photo" if depicts else "illustrative")
        log(f"{rel}  [{rec['license']}]  {rec['author']}" + (f"  -> beat {beat}" if beat else ""))
    return out


# ------------------------------------------------------------------ `music source`: licensed music that fits the trend's style
MUSIC_OK = {"cc0": "CC0", "pdm": "Public Domain", "by": "CC BY"}          # no NC, no ND, no SA: the channel may be monetised


def _music_queries(project: Path, query: str | None) -> list[str]:
    if query:
        return [query]
    qs = []
    ts = project / "research" / "trend-sounds.json"
    if ts.exists():
        st = [w for w, n in (load_json(ts).get("styles") or []) if n >= 2][:3]      # a style one video uses is not a trend
        if st:
            qs.append(" ".join(st) + " instrumental")
    brief = load_yaml(project / "brief.yaml") or {}
    if (brief.get("music") or {}).get("search"):
        qs.append(brief["music"]["search"])
    qs.append("instrumental background")
    return list(dict.fromkeys(qs))


def music_source(project, query: str | None = None, target: float | None = None, tries: int = 3) -> dict:
    """Find, verify, download and credit one CC0 / CC BY track for the project; otherwise report that the synthesised score is used.

    The licence is confirmed twice: in the search result and again on the track's own API record. Trimming, looping under the
    voice and ducking are done by render (`prepare_track` + the mix). Returns {"used": "licensed"|"synth", ...}."""
    project = ensure_project(project)
    from fvcore import load_json as _lj
    tl = next(iter(sorted((project / "build").glob("timeline-*.json"))), None)
    target = target or (_lj(tl).get("duration") if tl else None) or 30
    mdir = project / "assets" / "music"
    cands, seen = [], set()
    for q in _music_queries(project, query):
        try:
            d = fvnet.fetch_json("https://api.openverse.org/v1/audio/", {"q": q, "page_size": 20, "license": "cc0,pdm,by"})
        except Exception as e:                                          # noqa: BLE001
            warn(f"music source: search '{q}' failed: {str(e)[:80]}")
            continue
        for r in d.get("results", []):
            lic = (r.get("license") or "").lower()
            dur = (r.get("duration") or 0) / 1000
            if r["id"] in seen or lic not in MUSIC_OK or dur < 15 or dur > 900:
                continue
            seen.add(r["id"])
            cands.append((0 if dur >= target else 1, abs(dur - target), q, r))
    cands.sort(key=lambda c: c[:2])
    sc = project / "score.json"                    # projects must not all get the same track: the project's own seed picks among the best few
    if sc.exists() and len(cands) > 1:
        k = int(load_json(sc).get("seed") or 0) % min(len(cands), 6)
        cands = cands[k:] + cands[:k]
    fallback = {"used": "synth", "reason": "no suitable CC0 / CC BY track found" if not cands else "no candidate could be verified and downloaded"}
    for _, _, q, r in cands[: tries * 3]:
        try:
            det = fvnet.fetch_json(f"https://api.openverse.org/v1/audio/{r['id']}/")      # confirm the licence at the source record
        except Exception:                                               # noqa: BLE001
            continue
        lic = (det.get("license") or "").lower()
        if lic not in MUSIC_OK or not det.get("url"):
            continue
        label = MUSIC_OK[lic] + (f" {det.get('license_version') or '4.0'}" if lic == "by" else "")
        rec = _rec("openverse", det["id"], "music", det.get("title") or q, det.get("foreign_landing_url") or det.get("url"), det["url"], None,
                   duration=(det.get("duration") or 0) / 1000, author=det.get("creator"), author_url=det.get("creator_url"), lic=label, lic_url=det.get("license_url") or "")
        if fvnet.risk_of(rec) != "safe":
            continue
        ext = _ext(det["url"], "." + str(det.get("filetype") or "mp3").lower()[:5])
        dest = mdir / f"{fvnet.safe_name(rec['id'])}{ext}"
        try:
            fvnet.download_file(det["url"], dest, timeout=120, max_bytes=MAX_BYTES["music"], types=CTYPES["music"])
        except FishError as e:
            warn(f"music source: {rec['id']}: {str(e)[:80]}")
            continue
        for old in mdir.glob("*"):                                      # one track per project: render uses the first file in assets/music
            if old != dest and old.is_file():
                old.unlink()
        rec["file"] = str(dest.relative_to(project)).replace("\\", "/")
        rec["credit"] = fvnet.credit_line(rec)
        add_credit(project, rec)
        out = {"used": "licensed", "file": rec["file"], "title": rec["title"], "author": rec["author"], "license": rec["license"], "license_url": rec["license_url"],
               "source": rec["url"], "seconds": rec["duration"], "query": q, "credit": rec["credit"]}
        save_json(project / "build" / "music-source.json", out)
        log(f"music: licensed track {rec['title']} by {rec['author']} [{rec['license']}] -> {rec['file']}; credit written to assets/credits.json")
        return out
    save_json(project / "build" / "music-source.json", fallback)
    log(f"music: {fallback['reason']}: the synthesised score is used (mood and seed in score.json)")
    return fallback


def adopt(project, license: str, author: str, source: str, label: str | None = None, files: list[str] | None = None) -> dict:
    """For an existing project: write a credit record for every referenced picture that has none (using the licence, author and source the
    caller asserts), and set `label` on story/image/statement beats that lack one. Nothing is guessed: all three facts must be given."""
    import gates
    project = ensure_project(project)
    if not (license and author and source):
        raise FishError("adopt needs --license, --author and --source: you are asserting where the pictures come from")
    if label and label not in gates.LABELS:
        raise FishError(f"--label is one of: {', '.join(gates.LABELS)}")
    m = gates.measure(project)
    idx = gates.credit_index(project)
    added, labelled = [], []
    for r in m["rows"]:
        for x in r.get("srcs", []):
            if x.startswith("assets/") and (project / x).exists() and x not in idx and not (x.startswith("assets/shots/") or r["screenshot"]) and (not files or x in files):
                add_credit(project, {"id": "adopted-" + slugify(Path(x).stem), "provider": "adopted", "kind": "photo", "title": Path(x).stem, "file": x, "author": author,
                                     "license": license, "url": source, "credit": f"{Path(x).stem} by {author} ({source}), {license}.", "attribution_required": False, "risk": "safe"})
                idx[x] = {}
                added.append(x)
    if label:
        sbf = project / "storyboard.yaml"
        sb = load_yaml(sbf)
        for sc in sb.get("scenes", []):
            if sc.get("type") in gates.LABEL_TYPES and (sc.get("params") or {}).get("src") and not (sc["params"].get("label")):
                sc["params"]["label"] = label
                labelled.append(sc["id"])
        save_yaml(sbf, sb)
    log(f"adopted {len(added)} picture(s), labelled {len(labelled)} beat(s) as '{label}'" if label else f"adopted {len(added)} picture(s)")
    return {"credited": added, "labelled": labelled}


def plan_report(project) -> list[dict]:
    """Per beat: does it have a real image, and what is missing. (`fishvideo gates` enforces it.)"""
    import gates
    project = ensure_project(project)
    m = gates.measure(project)
    return [{"beat": r["id"], "type": r["type"], "kind": r["kind"], "images": r.get("srcs", [])} for r in m["rows"]]


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="assets.py", description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("search"); a.add_argument("project"); a.add_argument("q"); a.add_argument("--kind", default="photo", choices=KINDS)
    a.add_argument("--providers"); a.add_argument("-n", type=int, default=12)
    a.add_argument("--before", type=int, help="only works from before this year (wikimedia, archive)"); a.add_argument("--lang", help="language code (archive)")
    a.add_argument("--unverified", action="store_true", help="also list results that state no licence (they stay gated in `get`)")
    a = sp.add_parser("get"); a.add_argument("project"); a.add_argument("ids", nargs="+")
    a.add_argument("--accept-risk", action="store_true", help="download an asset whose licence is not verified")
    a = sp.add_parser("shot"); a.add_argument("project"); a.add_argument("urls", nargs="+"); a.add_argument("--width", type=int, default=1440)
    a.add_argument("--height", type=int, default=900); a.add_argument("--dpr", type=float, default=2); a.add_argument("--full", action="store_true")
    a.add_argument("--wait", type=float, default=2.5); a.add_argument("--keep-banners", action="store_true"); a.add_argument("--allow-private", action="store_true")
    a = sp.add_parser("logo"); a.add_argument("project"); a.add_argument("brand"); a.add_argument("--color", default="brand")
    a = sp.add_parser("icon"); a.add_argument("project"); a.add_argument("q"); a.add_argument("--color"); a.add_argument("-n", type=int, default=12)
    a = sp.add_parser("emoji"); a.add_argument("project"); a.add_argument("emoji"); a.add_argument("--set", dest="eset", default="openmoji", choices=["openmoji", "twemoji"])
    a = sp.add_parser("cutout"); a.add_argument("src"); a.add_argument("dst"); a.add_argument("--model", default="isnet-general-use")
    a = sp.add_parser("clip"); a.add_argument("project"); a.add_argument("src"); a.add_argument("clip_id")
    a.add_argument("--start", type=float, default=0); a.add_argument("--dur", type=float); a.add_argument("--fps", type=int, default=30); a.add_argument("--width", type=int, default=1080)
    a.add_argument("--grade", choices=sorted(GRADES)); a.add_argument("--sharpen", action="store_true"); a.add_argument("--lut", help=".cube file")
    a.add_argument("--aspect", choices=sorted(ASPECTS)); a.add_argument("--focus", help="x,y fractions of the frame to keep when cropping")
    a = sp.add_parser("sfx-pack"); a.add_argument("dest", nargs="?")
    a = sp.add_parser("source"); a.add_argument("project"); a.add_argument("q"); a.add_argument("--beat"); a.add_argument("-n", type=int, default=1)
    a.add_argument("--providers"); a.add_argument("--depicts", help="say the picture truly shows this person or event: the beat is labelled `archive photo` instead of `illustrative`")
    a.add_argument("--before", type=int); a.add_argument("--min-width", type=int, help="skip results narrower than this many px (default: the panel width at 2.2x)"); a.add_argument("--min-height", type=int, help="skip results shorter than this many px (default: half the frame height at 2.2x)")
    a = sp.add_parser("adopt"); a.add_argument("project"); a.add_argument("--license", required=True); a.add_argument("--author", required=True)
    a.add_argument("--source", required=True); a.add_argument("--label", choices=["archive photo", "illustrative"])
    a = sp.add_parser("music-source"); a.add_argument("project"); a.add_argument("--q"); a.add_argument("--target", type=float)
    a = sp.add_parser("plan"); a.add_argument("project")
    a = sp.add_parser("credits"); a.add_argument("project")
    ns = ap.parse_args(argv)
    if ns.cmd == "search":
        opts = {k: v for k, v in (("before", ns.before), ("lang", ns.lang)) if v}
        search(ns.project, ns.q, ns.kind, ns.providers.split(",") if ns.providers else None, ns.n, True if ns.unverified else None, **opts)
    elif ns.cmd == "get":
        return 0 if len(get(ns.project, ns.ids, ns.accept_risk)) == len(ns.ids) else 1
    elif ns.cmd == "shot":
        return 0 if shot(ns.project, ns.urls, ns.width, ns.height, ns.dpr, ns.full, ns.wait, ns.keep_banners, ns.allow_private) else 1
    elif ns.cmd in ("logo", "icon", "emoji"):
        import icons
        if ns.cmd == "logo":
            icons.logo(ns.project, ns.brand, ns.color)
        elif ns.cmd == "icon":
            icons.icon(ns.project, ns.q, ns.color, ns.n)
        else:
            icons.emoji(ns.project, ns.emoji, ns.eset)
    elif ns.cmd == "cutout":
        return 0 if cutout(ns.src, ns.dst, ns.model) else 1
    elif ns.cmd == "clip":
        focus = tuple(float(v) for v in ns.focus.split(",")) if ns.focus else None
        prep_clip(ns.project, ns.src, ns.clip_id, ns.start, ns.dur, ns.fps, ns.width, ns.grade, ns.sharpen, ns.lut, ns.aspect, focus)
    elif ns.cmd == "sfx-pack":
        sfx_pack(ns.dest)
    elif ns.cmd == "source":
        got = source(ns.project, ns.q, ns.beat, ns.n, ns.providers.split(",") if ns.providers else None, depicts=ns.depicts, before=ns.before, min_width=ns.min_width, min_height=ns.min_height)
        return 0 if got else 1
    elif ns.cmd == "adopt":
        adopt(ns.project, ns.license, ns.author, ns.source, ns.label)
    elif ns.cmd == "music-source":
        music_source(ns.project, ns.q, ns.target)
    elif ns.cmd == "plan":
        for r in plan_report(ns.project):
            log(f"{r['beat']:<22} {r['type']:<10} {r['kind']:<8} {', '.join(r['images']) or 'NEEDS an image: assets source <dir> \"<query>\" --beat ' + r['beat']}")
    elif ns.cmd == "credits":
        print(credits_text(ensure_project(ns.project)))
    return 0


if __name__ == "__main__":
    main_guard(cli)
