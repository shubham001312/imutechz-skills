"""YouTube research + (licence-guarded) download tool.

    python scripts/youtube.py search "motion graphics tutorial" [-n 20] [--recent-days 30]
    python scripts/youtube.py info <url>
    python scripts/youtube.py subs <url> [--lang en]
    python scripts/youtube.py download <url> --purpose reference|asset [--project P] [--dest D]
    python scripts/youtube.py clip <url> <start> <end> <dest> [--project P]
    python scripts/youtube.py suggest "motion graphics"

Search uses the Data API v3 when YOUTUBE_API_KEY is set (falls back to yt-dlp
on quota/network errors), otherwise yt-dlp `ytsearchN:` / `ytsearchdateN:` with
FULL metadata (not flat) so views, upload date, tags and licence are present.

Licence rule: purpose "reference" is for analysis only (<= 1080p, kept in
<project>/reference/ and never cut into a video). purpose "asset" and `clip`
are allowed ONLY when yt-dlp reports a Creative Commons licence; everything
else is refused. Allowed asset downloads are logged in assets/credits.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from fvcore import FishError, ffmpeg_bin, log, main_guard, secret, warn
import fvnet

API = "https://www.googleapis.com/youtube/v3"


def _ytdlp():
    try:
        import yt_dlp
        return yt_dlp
    except ImportError:
        raise FishError("yt-dlp is not installed: pip install yt-dlp")


def _base_opts(**extra) -> dict:
    o = {"quiet": True, "no_warnings": True, "noprogress": True, "socket_timeout": 20, "http_headers": {"User-Agent": fvnet.UA}}
    try:
        d = str(Path(ffmpeg_bin()).parent)
        o["ffmpeg_location"] = d
        # yt-dlp's partial-download check looks on PATH and ignores ffmpeg_location
        if d not in os.environ.get("PATH", ""):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    except FishError:
        pass
    o.update(extra)
    return o


# ------------------------------------------------------------------ helpers
def parse_time(t) -> float:
    """12, "12.5", "1:23", "01:02:03" -> seconds."""
    if isinstance(t, (int, float)):
        return float(t)
    parts = [float(x) for x in str(t).strip().split(":")]
    s = 0.0
    for p in parts:
        s = s * 60 + p
    return s


def _age_days(upload_date: str | None) -> float:
    try:
        d = dt.datetime.strptime(str(upload_date)[:8], "%Y%m%d").replace(tzinfo=dt.timezone.utc)
    except Exception:
        return 0.0
    return max((dt.datetime.now(dt.timezone.utc) - d).total_seconds() / 86400.0, 1.0)


def is_short(duration, width=None, height=None, url: str = "") -> bool:
    if "/shorts/" in (url or ""):
        return True
    if not duration or duration > 180:
        return False
    return True if not (width and height) else height > width


def normalize(e: dict) -> dict:
    """A yt-dlp info dict -> our record."""
    vid = e.get("id")
    views = e.get("view_count") or 0
    ud = e.get("upload_date") or ""
    age = _age_days(ud)
    url = e.get("webpage_url") or (f"https://www.youtube.com/watch?v={vid}" if vid else e.get("url", ""))
    return {
        "id": vid, "title": e.get("title") or "", "channel": e.get("channel") or e.get("uploader") or "",
        "views": views, "upload_date": ud, "duration": e.get("duration"),
        "views_per_day": round(views / age, 1) if age else 0.0,
        "tags": e.get("tags") or [], "url": url,
        "is_short": is_short(e.get("duration"), e.get("width"), e.get("height"), url),
        "likes": e.get("like_count"), "license": e.get("license"), "thumbnail": e.get("thumbnail"),
    }


def _iso_dur(s: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def _api_item(it: dict) -> dict:
    sn, st, cd = it.get("snippet", {}), it.get("statistics", {}), it.get("contentDetails", {})
    vid = it["id"] if isinstance(it["id"], str) else it["id"].get("videoId")
    views = int(st.get("viewCount") or 0)
    ud = (sn.get("publishedAt") or "")[:10].replace("-", "")
    dur = _iso_dur(cd.get("duration", ""))
    age = _age_days(ud)
    url = f"https://www.youtube.com/watch?v={vid}"
    lic = {"creativeCommon": "Creative Commons Attribution license (reuse allowed)", "youtube": "Standard YouTube License"}.get(it.get("status", {}).get("license", ""), None)
    return {
        "id": vid, "title": sn.get("title", ""), "channel": sn.get("channelTitle", ""), "views": views, "upload_date": ud,
        "duration": dur or None, "views_per_day": round(views / age, 1) if age else 0.0, "tags": sn.get("tags") or [], "url": url,
        "is_short": is_short(dur, None, None, url) if dur else False, "likes": int(st["likeCount"]) if "likeCount" in st else None,
        "license": lic, "thumbnail": (sn.get("thumbnails", {}).get("high") or {}).get("url"),
    }


def _api(path: str, key: str, **params) -> dict:
    return fvnet.fetch_json(f"{API}/{path}", dict(params, key=key))


def _api_videos(ids: list[str], key: str) -> list[dict]:
    out = []
    for i in range(0, len(ids), 50):
        d = _api("videos", key, part="snippet,statistics,contentDetails,status", id=",".join(ids[i:i + 50]))
        out += [_api_item(it) for it in d.get("items", [])]
    return out


def most_popular(region: str = "US", n: int = 25, category: str | None = None) -> list[dict]:
    """videos.list chart=mostPopular (needs YOUTUBE_API_KEY; [] without one)."""
    key = secret("YOUTUBE_API_KEY")
    if not key:
        return []
    try:
        d = _api("videos", key, part="snippet,statistics,contentDetails,status", chart="mostPopular", regionCode=region,
                 maxResults=min(max(n, 1), 50), videoCategoryId=category)
        return [_api_item(it) for it in d.get("items", [])]
    except fvnet.NetError as e:
        warn(f"mostPopular unavailable: {e}")
        return []


# ------------------------------------------------------------------ search
def _search_api(q: str, n: int, recent_days: int | None, key: str, order: str = "relevance", shorts: bool = False) -> list[dict]:
    p = dict(part="snippet", type="video", q=q, maxResults=min(n, 50), order=order)
    if shorts:
        p["videoDuration"] = "short"            # under 4 minutes; vertical-only filtering happens after
    if recent_days:
        p["publishedAfter"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=recent_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    d = _api("search", key, **p)
    ids = [it["id"]["videoId"] for it in d.get("items", []) if it.get("id", {}).get("videoId")]
    return _api_videos(ids, key) if ids else []


def _search_ytdlp(q: str, n: int, recent_days: int | None, shorts: bool = False) -> list[dict]:
    yt = _ytdlp()
    count = n if not recent_days else min(n * 2, 60)
    opts = _base_opts(skip_download=True, ignoreerrors=True, extract_flat=False)
    if recent_days:
        # ytsearchdate: is rejected by current yt-dlp, so use the results page with YouTube's own filter:
        # uploaded this week / month / year, sorted by views. That is what "trending now" means here.
        from urllib.parse import quote_plus
        sp = "CAMSBAgDEAE%3D" if recent_days <= 7 else "CAMSBAgEEAE%3D" if recent_days <= 31 else "CAMSBAgFEAE%3D"
        if shorts:      # same filter plus "under 4 minutes" (protobuf field 3 = 1); without it a Shorts query returns mostly long videos
            sp = {"CAMSBAgDEAE%3D": "CAMSBggDEAEYAQ%3D%3D", "CAMSBAgEEAE%3D": "CAMSBggEEAEYAQ%3D%3D", "CAMSBAgFEAE%3D": "CAMSBggFEAEYAQ%3D%3D"}[sp]
        target = f"https://www.youtube.com/results?search_query={quote_plus(q)}&sp={sp}"
        opts["playlistend"] = count
    else:
        target = f"ytsearch{count}:{q}"
    with yt.YoutubeDL(opts) as y:
        res = y.extract_info(target, download=False) or {}
    out = [normalize(e) for e in (res.get("entries") or []) if e]
    if recent_days:
        cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=recent_days)).strftime("%Y%m%d")
        out = [v for v in out if (v["upload_date"] or "0") >= cut]
    return out[:n]


def search_hashtag_shorts(tag: str, n: int = 20, recent_days: int | None = None) -> list[dict]:
    """Real Shorts from a hashtag's Shorts feed (the results page rarely lists any). Records as `search`; recent ones only."""
    tag = re.sub(r"[^a-z0-9]", "", tag.lower())
    if len(tag) < 3:
        return []
    try:
        yt = _ytdlp()
        opts = _base_opts(skip_download=True, ignoreerrors=True, extract_flat=False)
        opts["playlistend"] = n
        with yt.YoutubeDL(opts) as y:
            res = y.extract_info(f"https://www.youtube.com/hashtag/{tag}/shorts", download=False) or {}
    except Exception as e:
        warn(f"hashtag feed #{tag} failed: {str(e)[:120]}")
        return []
    out = [normalize(e) for e in (res.get("entries") or []) if e]
    for v in out:
        v["is_short"] = bool(v["duration"] and v["duration"] <= 180)
    if recent_days:
        cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=recent_days)).strftime("%Y%m%d")
        out = [v for v in out if (v["upload_date"] or "0") >= cut]
    return out[:n]


def search(q: str, n: int = 20, recent_days: int | None = None, shorts: bool = False) -> list[dict]:
    """Search YouTube. Records: id,title,channel,views,upload_date,duration,views_per_day,tags,url,is_short."""
    key = secret("YOUTUBE_API_KEY")
    if key:
        try:
            return _search_api(q, n, recent_days, key, shorts=shorts)
        except fvnet.NetError as e:
            warn(f"YouTube Data API failed ({e}); falling back to yt-dlp")
    try:
        return _search_ytdlp(q, n, recent_days, shorts)
    except FishError:
        raise
    except Exception as e:
        warn(f"yt-dlp search failed: {str(e)[:200]}")
        return []


def suggest(q: str) -> list[str]:
    """YouTube autocomplete (unofficial, key-less)."""
    try:
        raw = fvnet.fetch("https://suggestqueries.google.com/complete/search", {"client": "firefox", "ds": "yt", "q": q})
        d = json.loads(raw.decode("utf-8", "replace"))
        return [str(x) for x in d[1]] if isinstance(d, list) and len(d) > 1 else []
    except (fvnet.NetError, ValueError) as e:
        warn(f"autocomplete unavailable: {e}")
        return []


# ------------------------------------------------------------------ info
def info(url: str) -> dict:
    """Full metadata for one video: normalized record + licence, chapters, description, size."""
    yt = _ytdlp()
    with yt.YoutubeDL(_base_opts(skip_download=True)) as y:
        e = y.extract_info(url, download=False)
    r = normalize(e)
    r.update({"chapters": e.get("chapters") or [], "description": e.get("description") or "", "width": e.get("width"),
              "height": e.get("height"), "categories": e.get("categories") or [], "channel_url": e.get("channel_url"),
              "channel_id": e.get("channel_id"),
              **{k: e.get(k) for k in ("track", "artist", "album", "creator") if e.get(k)}})
    return r


# ------------------------------------------------------------------ subtitles
_TAG = re.compile(r"<[^>]+>")


def _ts(s: str) -> float:
    m = re.match(r"(?:(\d+):)?(\d\d):(\d\d)[.,](\d{3})", s.strip())
    if not m:
        return 0.0
    h, mi, se, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(se) + int(ms) / 1000


def parse_vtt(text: str) -> list[dict]:
    """VTT (incl. YouTube's rolling auto-captions) -> de-duplicated [{start,end,text}] lines."""
    out: list[dict] = []
    last = ""
    for block in re.split(r"\n\s*\n", text.replace("\r", "")):
        lines = [l for l in block.split("\n") if l.strip()]
        tl = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if tl is None:
            continue
        a, b = lines[tl].split("-->")[:2]
        start, end = _ts(a), _ts(b.split()[0])
        for l in lines[tl + 1:]:
            t = re.sub(r"\s+", " ", _TAG.sub("", l)).strip()
            if t and t != last:
                out.append({"start": round(start, 2), "end": round(end, 2), "text": t})
                last = t
    return out


def first_sentence(text: str, max_words: int = 22) -> str:
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    s = m.group(1) if m else text
    w = s.split()
    return " ".join(w[:max_words]) + ("..." if len(w) > max_words else "")


def subs(url: str, lang: str = "en") -> dict:
    """Manual or auto subtitles -> {lang, auto, cues:[{start,end,text}], text, hook}. Retries 429 with backoff."""
    yt = _ytdlp()
    tmp = Path(tempfile.mkdtemp(prefix="fvsubs-"))
    seen429: list[str] = []

    class _L:
        def debug(self, m): pass
        def info(self, m): pass
        def warning(self, m):
            if "429" in str(m):
                seen429.append(str(m))
        def error(self, m):
            if "429" in str(m):
                seen429.append(str(m))

    opts = _base_opts(skip_download=True, writesubtitles=True, writeautomaticsub=True, subtitleslangs=[lang, f"{lang}-*"],
                      subtitlesformat="vtt", outtmpl=str(tmp / "%(id)s.%(ext)s"), logger=_L())
    try:
        for attempt in range(4):
            seen429.clear()
            try:
                with yt.YoutubeDL(opts) as y:
                    y.extract_info(url, download=True)
            except Exception as e:
                if "429" in str(e) and attempt < 3:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise FishError(f"subtitle fetch failed: {str(e)[:200]}")
            files = sorted(tmp.glob("*.vtt"))
            if files or not seen429 or attempt == 3:
                break
            time.sleep(2 ** (attempt + 1))
        if not files:
            warn("no subtitles available for this video")
            return {"lang": lang, "cues": [], "text": "", "hook": ""}
        cues = parse_vtt(files[0].read_text(encoding="utf-8", errors="replace"))
        text = " ".join(c["text"] for c in cues)
        return {"lang": lang, "cues": cues, "text": text, "hook": first_sentence(text)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ licence guard + downloads
def is_creative_commons(meta: dict) -> bool:
    return "creative commons" in str(meta.get("license") or "").lower()


def require_cc(meta: dict, what: str = "download as an asset") -> None:
    if not is_creative_commons(meta):
        raise FishError(
            f"refusing to {what}: '{meta.get('title', '?')}' has licence '{meta.get('license') or 'Standard YouTube License'}', "
            "not Creative Commons. Only CC-licensed YouTube videos may be reused. Use purpose='reference' for analysis only, "
            "or find footage on Pexels/Pixabay/NASA/Wikimedia (assets.py search).")


def _log_credit(project: Path | None, meta: dict, file: Path) -> None:
    if not project:
        warn("could not locate the project (no brief.yaml above dest): credit not logged")
        return
    chan = meta.get("channel") or meta.get("uploader") or "unknown"
    rec = {"id": meta.get("id"), "provider": "youtube", "kind": "video", "title": meta.get("title"), "url": meta.get("url") or meta.get("webpage_url"),
           "author": chan, "author_url": meta.get("channel_url") or "", "license": "CC BY (YouTube Creative Commons)",
           "license_url": "https://creativecommons.org/licenses/by/3.0/", "attribution_required": True,
           "file": str(file.relative_to(project)) if str(file).startswith(str(project)) else str(file)}
    fvnet.add_credit(project, rec)


def _resolve_dest(dest, project, purpose, default_sub: str) -> tuple[Path, str | None]:
    """-> (directory, fixed_stem_or_None)."""
    if dest in (None, "") and project:
        return Path(project) / default_sub, None
    d = Path(dest)
    if d.suffix:
        return d.parent, d.stem
    return d, None


def download(url: str, dest=None, purpose: str = "reference", project=None, max_height: int = 1080) -> Path:
    """Download a video. purpose='reference' (analysis only) or 'asset' (Creative Commons only)."""
    if purpose not in ("reference", "asset"):
        raise FishError("purpose must be 'reference' or 'asset'")
    yt = _ytdlp()
    meta = None
    if purpose == "asset":
        meta = info(url)
        require_cc(meta)
    outdir, stem = _resolve_dest(dest, project, purpose, "reference" if purpose == "reference" else "assets/video")
    outdir.mkdir(parents=True, exist_ok=True)
    tmpl = (stem or ("ref-%(id)s" if purpose == "reference" else "youtube-%(id)s")) + ".%(ext)s"
    opts = _base_opts(outtmpl=str(outdir / tmpl), merge_output_format="mp4",
                      format=f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b")
    with yt.YoutubeDL(opts) as y:
        e = y.extract_info(url, download=True)
        path = Path(y.prepare_filename(e))
    if not path.exists():
        path = path.with_suffix(".mp4")
    if not path.exists():
        raise FishError("download finished but the file was not found")
    if purpose == "reference":
        log(f"reference saved (analysis only, never cut into the video): {path}")
    else:
        _log_credit(Path(project) if project else fvnet.project_of(outdir), meta, path)
        log(f"CC asset saved + credit logged: {path}")
    return path


def clip(url: str, start, end, dest, project=None) -> Path:
    """Download only [start, end] of a Creative-Commons video (refused otherwise)."""
    yt = _ytdlp()
    meta = info(url)
    require_cc(meta, "cut a clip")
    s, e = parse_time(start), parse_time(end)
    if e <= s:
        raise FishError("clip end must be after start")
    outdir, stem = _resolve_dest(dest, project, "asset", "assets/video")
    outdir.mkdir(parents=True, exist_ok=True)
    tmpl = (stem or f"youtube-{meta['id']}-{int(s)}-{int(e)}") + ".%(ext)s"
    opts = _base_opts(outtmpl=str(outdir / tmpl), merge_output_format="mp4", format="bv*[height<=1080]+ba/b[height<=1080]/b",
                      download_ranges=yt.utils.download_range_func(None, [(s, e)]), force_keyframes_at_cuts=True)
    with yt.YoutubeDL(opts) as y:
        r = y.extract_info(url, download=True)
        path = Path(y.prepare_filename(r))
    if not path.exists():
        path = path.with_suffix(".mp4")
    _log_credit(Path(project) if project else fvnet.project_of(outdir), meta, path)
    log(f"CC clip saved + credit logged: {path}")
    return path


# ------------------------------------------------------------------ CLI
def _fmt(v: dict) -> str:
    d = v.get("duration") or 0
    return f"{v['views']:>10,}  {v['views_per_day']:>9,.0f}/d  {int(d)//60}:{int(d)%60:02d}{' S' if v['is_short'] else '  '}  {v['title'][:70]}  [{v['channel'][:24]}]  {v['url']}"


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="youtube.py", description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("search"); a.add_argument("q"); a.add_argument("-n", type=int, default=20); a.add_argument("--recent-days", type=int); a.add_argument("--json", action="store_true")
    a = sp.add_parser("info"); a.add_argument("url")
    a = sp.add_parser("subs"); a.add_argument("url"); a.add_argument("--lang", default="en"); a.add_argument("--json", action="store_true")
    a = sp.add_parser("download"); a.add_argument("url"); a.add_argument("--purpose", choices=["reference", "asset"], default="reference"); a.add_argument("--dest"); a.add_argument("--project")
    a = sp.add_parser("clip"); a.add_argument("url"); a.add_argument("start"); a.add_argument("end"); a.add_argument("dest"); a.add_argument("--project")
    a = sp.add_parser("suggest"); a.add_argument("q")
    ns = ap.parse_args(argv)
    if ns.cmd == "search":
        res = search(ns.q, ns.n, ns.recent_days)
        if ns.json:
            print(json.dumps(res, indent=1, ensure_ascii=False))
        else:
            for v in res:
                log(_fmt(v))
            if not res:
                warn("no results")
    elif ns.cmd == "info":
        print(json.dumps(info(ns.url), indent=1, ensure_ascii=False))
    elif ns.cmd == "subs":
        r = subs(ns.url, ns.lang)
        print(json.dumps(r, indent=1, ensure_ascii=False) if ns.json else f"hook: {r['hook']}\n\n{r['text']}")
    elif ns.cmd == "download":
        download(ns.url, ns.dest, ns.purpose, ns.project)
    elif ns.cmd == "clip":
        clip(ns.url, ns.start, ns.end, ns.dest, ns.project)
    elif ns.cmd == "suggest":
        for s in suggest(ns.q):
            log(s)
    return 0


if __name__ == "__main__":
    main_guard(cli)
