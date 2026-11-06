"""Live trend research for a video: the source of its direction. Nothing about what is trending is stored in this repo.

    fishvideo trends <project> [--topic "..."] [--format shorts|long] [--days 30] [-n 30]   fetch recent results, contact sheet
    fishvideo trends <project> --derive-theme                          a project-local theme from the fetched thumbnails
    fishvideo trends <project> --unavailable "<reason>"                search is really down: recorded, built-in themes are the fallback
    fishvideo trends <project> --check                                 the same check `gate` runs

`trends` searches the project's topic in its format over the last 30 days (widened to 90 when thin), ranks by views
per day, separates Shorts from long videos, writes research/trends.json and trends.md, downloads the top thumbnails
into research/trend-thumbs/ and a contact sheet research/trends-contact.jpg that you must open. Then YOU write the
Analysis and a `direction` block in trends.md (see gate_problems). These files are for analysis only: never use them in the
video, never commit or package them. Never copy a result's script, images or look.

Older all-in-one mode (`trends()`), kept for tests:
    python scripts/trends.py <project> --topic "AI agents" [--region IN] [--days 30] [-n 40]

Combines (all optional, each fails soft): yt-dlp / Data API search for the
topic (recent and all-time), YouTube autocomplete, and the Data API
`chart=mostPopular` when YOUTUBE_API_KEY exists. Ranks by views_per_day, then
extracts title patterns, keywords, tags, typical durations and the top-10
hooks (first sentence of the auto-subs for the top 5, best effort).

Writes <project>/research/trends.json and trends.md with recommendations:
title formulas, <= 15 tags, 3-5 hashtags and an ideal length.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import statistics
from collections import Counter
from pathlib import Path

from fvcore import ensure_project, log, main_guard, save_json, warn
import youtube

STOP = set("""a an the and or but of to in on for with at by from is are was were be been it its this that these those you your
i we they he she as not no yes do does did can will just so if than then how what why when who which about into out up down
over under more most very new vs via per my our their me us them have has had get got""".split())
POWER = ["secret", "ultimate", "best", "free", "easy", "fast", "insane", "stop", "never", "mistake", "mistakes", "worst", "truth", "proven",
         "simple", "instantly", "amazing", "shocking", "hidden", "powerful", "beginner", "beginners", "complete", "guide", "tutorial",
         "tips", "tricks", "hack", "hacks", "why", "how", "now", "finally", "real", "actually", "wrong", "must", "only", "essential"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F2FF⭐⬆⏩-⏳]")
FORMULAS = [
    ("number-list", r"^\s*\d+\b|\b\d+\s+(ways|things|tips|tricks|reasons|mistakes|ideas|steps|tools)\b", "N things/ways/tips to ... (e.g. '7 mistakes that ...')"),
    ("how-to", r"^\s*how\s+to\b|\bhow\s+i\b", "How to <result> (in <time>) / How I <result>"),
    ("question", r"\?|^\s*(why|what|is|are|can|do|does|should)\b", "Why/What/Can ...? (curiosity question)"),
    ("mistakes-warning", r"\b(mistake|mistakes|stop|never|don't|dont|worst|wrong|avoid)\b", "Stop/Never/Avoid ... (warning or mistake framing)"),
    ("versus", r"\bvs\.?\b|\bversus\b|\bor\b.*\?", "A vs B (comparison)"),
    ("ultimate-guide", r"\b(ultimate|complete|full|beginner'?s?|masterclass|crash course|guide|tutorial)\b", "The complete/ultimate guide to ..."),
    ("time-box", r"\bin\s+\d+\s*(minutes?|mins?|seconds?|secs?|days?|hours?)\b|\b\d+\s*(minute|min|second|day|hour)s?\b", "... in N minutes/days (time-boxed promise)"),
    ("secret-reveal", r"\b(secret|truth|hidden|nobody|no one|they don't|exposed|revealed)\b", "The secret/truth about ... (reveal)"),
]


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9'+#.-]*", text.lower()) if w not in STOP and len(w) > 2 and not w.isdigit()]


def title_patterns(titles: list[str]) -> dict:
    n = max(len(titles), 1)
    lens = [len(t) for t in titles] or [0]
    wc = [len(t.split()) for t in titles] or [0]
    caps = sum(1 for t in titles if any(w.isupper() and len(w) >= 3 and w.isalpha() for w in t.split()))
    low = [t.lower() for t in titles]
    power = Counter(w for t in low for w in set(re.findall(r"[a-z']+", t)) if w in POWER)
    return {
        "count": len(titles), "avg_chars": round(sum(lens) / n, 1), "median_chars": statistics.median(lens), "avg_words": round(sum(wc) / n, 1),
        "pct_number": round(100 * sum(1 for t in titles if re.search(r"\d", t)) / n),
        "pct_question": round(100 * sum(1 for t in titles if "?" in t or re.match(r"\s*(why|what|how|is|are|can|do|does|should)\b", t, re.I)) / n),
        "pct_statement": round(100 * sum(1 for t in titles if "?" not in t and not re.match(r"\s*(why|what|how|is|are|can|do|does|should)\b", t, re.I)) / n),
        "pct_caps_word": round(100 * caps / n), "pct_emoji": round(100 * sum(1 for t in titles if EMOJI.search(t)) / n),
        "pct_brackets": round(100 * sum(1 for t in titles if re.search(r"[\(\[].+[\)\]]", t)) / n),
        "power_words": power.most_common(10),
    }


def detect_formulas(ranked: list[dict]) -> list[dict]:
    """Which title formulas the top videos use, weighted by views_per_day."""
    res = []
    total = sum(v["views_per_day"] for v in ranked) or 1
    for name, rx, tmpl in FORMULAS:
        hit = [v for v in ranked if re.search(rx, v["title"], re.I)]
        if not hit:
            continue
        res.append({"formula": name, "template": tmpl, "videos": len(hit), "share_of_views_per_day": round(100 * sum(v["views_per_day"] for v in hit) / total),
                    "example": hit[0]["title"]})
    return sorted(res, key=lambda r: r["share_of_views_per_day"], reverse=True)


def keywords_and_tags(ranked: list[dict], topic: str, limit_tags: int = 15) -> tuple[list[tuple[str, int]], list[str]]:
    kw = Counter()
    tagc = Counter()
    for v in ranked:
        for w in set(_words(v["title"])):
            kw[w] += 1
        for t in v.get("tags") or []:
            t = t.strip().lower()
            if 1 < len(t) <= 30:
                tagc[t] += 1
    tags = [t for t, _ in tagc.most_common(limit_tags * 2)]
    topic_l = topic.strip().lower()
    out = [topic_l] if topic_l else []
    for t in tags + [w for w, _ in kw.most_common(30)]:
        if t not in out:
            out.append(t)
        if len(out) >= limit_tags:
            break
    return kw.most_common(25), out[:limit_tags]


def make_hashtags(topic: str, keywords: list[tuple[str, int]], k: int = 4) -> list[str]:
    out: list[str] = []
    for cand in ["".join(_words(topic)[:3])] + [w for w, _ in keywords]:
        h = "#" + re.sub(r"[^a-z0-9]", "", cand.lower())
        if len(h) > 2 and h not in out:
            out.append(h)
        if len(out) >= k:
            break
    return out[:5] if len(out) >= 3 else out


def duration_stats(ranked: list[dict]) -> dict:
    ds = [v["duration"] for v in ranked if v.get("duration")]
    top = [v["duration"] for v in ranked[:10] if v.get("duration")]
    shorts = [v for v in ranked if v.get("duration")]
    if not ds:
        return {"typical_s": None}
    qs = statistics.quantiles(top, n=4) if len(top) >= 4 else [min(top or ds), statistics.median(top or ds), max(top or ds)]
    return {"typical_s": round(statistics.median(ds)), "top10_median_s": round(statistics.median(top or ds)), "top10_p25_p75_s": [round(qs[0]), round(qs[-1])],
            "pct_shorts": round(100 * sum(1 for v in shorts if v["is_short"]) / max(len(shorts), 1))}


def dedupe(vids: list[dict]) -> list[dict]:
    seen, out = set(), []
    for v in vids:
        if v.get("id") and v["id"] not in seen:
            seen.add(v["id"])
            out.append(v)
    return out


def recommend(topic: str, ranked: list[dict], formulas: list[dict], tags: list[str], hashtags: list[str], dur: dict, pat: dict) -> dict:
    ideal = None
    if dur.get("top10_p25_p75_s"):
        lo, hi = dur["top10_p25_p75_s"]
        ideal = {"seconds": [lo, hi], "note": "shorts-length (<= 60 s vertical)" if (dur["top10_median_s"] or 999) <= 60 else "long-form" if hi > 240 else "mid-length"}
    tl = int(pat["median_chars"]) if pat["count"] else 55
    return {
        "title_formulas": [{"formula": f["formula"], "template": f["template"], "example": f["example"]} for f in formulas[:3]],
        "title_rules": [f"aim for about {tl} characters (top titles average {pat['avg_chars']})",
                        "put a number in the title" if pat["pct_number"] >= 40 else "numbers are optional here",
                        "phrase it as a question" if pat["pct_question"] >= 40 else "statement titles dominate; lead with the payoff",
                        "use one ALL-CAPS word at most" if pat["pct_caps_word"] >= 25 else "avoid shouting caps",
                        "emoji are common" if pat["pct_emoji"] >= 30 else "skip emoji"],
        "tags": tags[:15], "hashtags": hashtags[:5], "ideal_length": ideal,
    }


def _hooks(top: list[dict], n_subs: int = 5) -> None:
    for i, v in enumerate(top):
        v["hook"] = ""
        if i < n_subs:
            try:
                v["hook"] = youtube.subs(v["url"])["hook"]
            except Exception as e:
                warn(f"hook skipped for {v['id']}: {str(e)[:90]}")


def trends(project, topic: str, region: str = "US", days: int = 30, n: int = 40, hooks: bool = True) -> dict:
    project = ensure_project(project)
    log(f"researching '{topic}' (region {region}, last {days} days) ...")
    recent = youtube.search(topic, n, recent_days=days)
    alltime = youtube.search(topic, n)
    sugg = youtube.suggest(topic)
    for extra in ("how to " + topic, topic + " tutorial"):
        sugg += [s for s in youtube.suggest(extra) if s not in sugg]
    popular = youtube.most_popular(region, 25)
    ranked = sorted(dedupe(recent + alltime), key=lambda v: v["views_per_day"], reverse=True)[:n]
    if not ranked:
        warn("no videos found: results will be empty (offline, rate limited, or yt-dlp needs updating)")
    top = [dict(v) for v in ranked[:10]]
    if hooks and top:
        _hooks(top)
    titles = [v["title"] for v in ranked]
    pat = title_patterns(titles)
    formulas = detect_formulas(ranked)
    kws, tags = keywords_and_tags(ranked, topic)
    hashtags = make_hashtags(topic, kws)
    dur = duration_stats(ranked)
    rec = recommend(topic, ranked, formulas, tags, hashtags, dur, pat)
    data = {"topic": topic, "region": region, "days": days, "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "source": "youtube-data-api" if youtube.secret("YOUTUBE_API_KEY") else "yt-dlp",
            "ranked": [{k: v[k] for k in ("id", "title", "channel", "views", "upload_date", "duration", "views_per_day", "is_short", "url")} for v in ranked],
            "top10": [{k: v.get(k) for k in ("id", "title", "channel", "views", "views_per_day", "duration", "url", "hook")} for v in top],
            "patterns": pat, "formulas": formulas, "keywords": kws, "durations": dur, "suggestions": sugg,
            "most_popular": [{k: v[k] for k in ("id", "title", "channel", "views", "views_per_day", "url")} for v in popular[:15]],
            "recommendations": rec}
    out = project / "research"
    save_json(out / "trends.json", data)
    (out / "trends.md").write_text(render_md(data), encoding="utf-8")
    log(f"wrote {out / 'trends.json'} and trends.md ({len(ranked)} videos)")
    return data


def render_md(d: dict) -> str:
    r, p = d["recommendations"], d["patterns"]
    L = [f"# Trends: {d['topic']}", f"_{d['generated']} | region {d['region']} | last {d['days']} days | source {d['source']}_", "", "## Recommendations", "",
         "**Title formulas**"]
    L += [f"- `{f['formula']}`: {f['template']}  \n  e.g. \"{f['example']}\"" for f in r["title_formulas"]] or ["- (no data)"]
    L += ["", "**Title rules**"] + [f"- {x}" for x in r["title_rules"]]
    il = r["ideal_length"]
    L += ["", f"**Ideal length**: {il['seconds'][0]}-{il['seconds'][1]} s ({il['note']})" if il else "**Ideal length**: unknown",
          "", f"**Tags ({len(r['tags'])})**: " + ", ".join(r["tags"]), "", "**Hashtags**: " + " ".join(r["hashtags"]), "",
          "## Title patterns", "",
          f"- {p['count']} titles, median {p['median_chars']} chars, {p['avg_words']} words",
          f"- numbers {p['pct_number']}%, questions {p['pct_question']}%, ALL-CAPS word {p['pct_caps_word']}%, emoji {p['pct_emoji']}%, brackets {p['pct_brackets']}%",
          "- power words: " + (", ".join(f"{w} ({c})" for w, c in p["power_words"]) or "none"), "", "## Top 10 by views per day", ""]
    for i, v in enumerate(d["top10"], 1):
        L.append(f"{i}. **{v['title']}** ({v['channel']}) - {v['views']:,} views, {v['views_per_day']:,.0f}/day, {int(v['duration'] or 0)} s  \n   {v['url']}")
        if v.get("hook"):
            L.append(f"   - hook: \"{v['hook']}\"")
    L += ["", "## Keywords", "", ", ".join(f"{w} ({c})" for w, c in d["keywords"]), "", "## Autocomplete", ""] + [f"- {s}" for s in d["suggestions"][:25]]
    if d["most_popular"]:
        L += ["", f"## Most popular now ({d['region']})", ""] + [f"- {v['title']} ({v['channel']})" for v in d["most_popular"]]
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ live research, enforced by the gate
STALE_DAYS = 14
MIN_RESULTS = 5
SHORT_PLATFORMS = {"shorts", "reels", "tiktok"}
ANALYSIS_HEAD = "## Analysis (written by you after opening the contact sheet)"
DIRECTION_KEYS = ("hook", "pacing", "layout", "thumbnail", "palette")
_TODO = re.compile(r"TODO|<[^<>\n]{2,80}>", re.I)


def format_of(brief: dict) -> str:
    plats = {str(p).lower() for p in (brief.get("platforms") or [])}
    return "shorts" if plats & SHORT_PLATFORMS and not ("youtube" in plats) else "long"


def topic_of(brief: dict) -> str:
    ans = (brief.get("interview") or {}).get("answers") or {}
    t = ans.get("topic") or brief.get("title") or brief.get("prompt") or ""
    return re.split(r"[\n]", str(t))[0][:120].strip()


def _fetch_recent(topic: str, fmt: str, days: int, n: int) -> tuple[list[dict], list[str], int]:
    queries = ([f"{topic} #shorts", topic] if fmt == "shorts" else [topic, f"{topic} explained"])
    used = days
    found: list[dict] = []
    for window in (days, 90) if days < 90 else (days,):
        found = []
        for q in queries:
            found += youtube.search(q, n, recent_days=window, shorts=(fmt == "shorts"))
        if fmt == "shorts":                                   # the results page lists few real Shorts: add the hashtag Shorts feeds
            ws = _words(topic)
            need = 2 if len(ws) >= 3 else 1                   # a hashtag feed is broad: keep only results that mention the topic's words
            def on_topic(v):
                blob = (v["title"] + " " + " ".join(v.get("tags") or [])).lower()
                return sum(1 for w in set(ws) if w in blob) >= need
            joined = "".join(ws[:2])
            feeds = [joined] + [w for w in ws if len(w) >= 4 and w != joined][:3]
            got = 0
            for tag in dict.fromkeys(feeds):
                part = [v for v in youtube.search_hashtag_shorts(tag, n, window) if on_topic(v)]
                found += part
                got += len(part)
                if got >= 10:
                    break
        found = dedupe(found)
        used = window
        if sum(1 for v in found if v["is_short"] == (fmt == "shorts")) >= 10:
            break
    return found, queries, used


def _thumb_url(v: dict) -> str | None:
    return v.get("thumbnail") or (f"https://i.ytimg.com/vi/{v['id']}/hqdefault.jpg" if v.get("id") else None)


def contact_sheet(rows: list[dict], out_dir: Path, k: int = 12) -> Path | None:
    """Download the top thumbnails (analysis only) and tile them, numbered. Returns the sheet path, or None."""
    import fvnet
    from PIL import Image, ImageDraw
    tiles = []
    d = out_dir / "trend-thumbs"
    for i, v in enumerate(rows[:k], 1):
        u = _thumb_url(v)
        if not u:
            continue
        try:
            f = fvnet.download_file(u, d / f"{i:02d}-{v['id']}.jpg", max_bytes=3 << 20, types=("image/",))
            v["thumb_file"] = f"trend-thumbs/{f.name}"
            tiles.append((i, Image.open(f).convert("RGB")))
        except Exception as e:
            warn(f"thumbnail {i} skipped: {str(e)[:80]}")
    if not tiles:
        return None
    W, H, cols = 320, 180, 4
    rws = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * W, rws * H), (20, 20, 20))
    dr = ImageDraw.Draw(sheet)
    for j, (i, im) in enumerate(tiles):
        sheet.paste(im.resize((W, H)), ((j % cols) * W, (j // cols) * H))
        dr.rectangle([(j % cols) * W, (j // cols) * H, (j % cols) * W + 26, (j // cols) * H + 20], fill=(0, 0, 0))
        dr.text(((j % cols) * W + 6, (j // cols) * H + 4), str(i), fill=(255, 255, 255))
    out = out_dir / "trends-contact.jpg"
    sheet.save(out, quality=82)
    return out


def _analysis_template(fmt: str) -> str:
    return "\n".join([ANALYSIS_HEAD, "",
        "Open research/trends-contact.jpg and the rows above. Cite result numbers (#n) from THIS run; if fewer than 5 real results, say the data is thin and claim no trend.", "",
        "- Hook pattern: TODO", "- Pacing: TODO", "- Thumbnail pattern (words, faces, tiles, layout): TODO", "- Colour pattern: TODO",
        "- Closest built-in theme and why (fallback only): TODO", "- What this video takes (ideas, never a script, image or look): TODO", "",
        "```yaml", "direction:", "  hook: TODO (approach, citing #n)", "  pacing: TODO (cuts per 10 s, line length, citing #n)",
        "  layout: TODO (beat order and scene layouts this video will use)", "  thumbnail: TODO (words and tile choice)",
        "  palette: TODO (from --derive-theme, or the fallback theme)", "```", ""])


def render_recent_md(d: dict) -> str:
    L = [f"# Trend research: {d['topic']}", f"_{d['generated']} | format {d['format']} | last {d['days_used']} days | queries: {'; '.join(d['queries'])} | source {d['source']}_", "",
         f"{d['counts']['shorts']} Shorts and {d['counts']['long']} long videos found; {len(d['results'])} ranked here." + (" **Data is thin: claim no trend.**" if d["thin"] else ""), "",
         "| # | title | channel | views | views/day | length | url |", "|---|---|---|---|---|---|---|"]
    for i, v in enumerate(d["results"], 1):
        L.append(f"| {i} | {v['title'][:70].replace('|', '/')} | {v['channel'][:24].replace('|', '/')} | {v['views']:,} | {v['views_per_day']:,.0f} | {int(v['duration'] or 0)} s | {v['url']} |")
    L += ["", "Contact sheet: `research/trends-contact.jpg` (open it). Analysis only: do not use, commit or package these files.", ""]
    return "\n".join(L)


def recent(project, topic: str | None = None, fmt: str | None = None, days: int = 30, n: int = 30) -> dict:
    project = ensure_project(project)
    from fvcore import load_yaml
    brief = load_yaml(project / "brief.yaml") or {}
    topic = topic or topic_of(brief)
    fmt = fmt or format_of(brief)
    if not topic:
        raise SystemExit("trends: no topic (pass --topic)")
    log(f"live search: '{topic}' ({fmt}, last {days} days, widened to 90 if thin) ...")
    found, queries, used = _fetch_recent(topic, fmt, days, n)
    want_short = fmt == "shorts"
    same = sorted([v for v in found if v["is_short"] == want_short], key=lambda v: v["views_per_day"], reverse=True)
    other = [v for v in found if v["is_short"] != want_short]
    ranked = same[:n]
    out = project / "research"
    out.mkdir(parents=True, exist_ok=True)
    sheet = contact_sheet(ranked, out) if ranked else None
    keep = ("id", "title", "channel", "views", "upload_date", "duration", "views_per_day", "is_short", "url", "thumb_file")
    data = {"topic": topic, "format": fmt, "days_used": used, "queries": queries, "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "source": "youtube-data-api" if youtube.secret("YOUTUBE_API_KEY") else "yt-dlp",
            "results": [{k: v.get(k) for k in keep} for v in ranked],
            "counts": {"shorts": sum(1 for v in found if v["is_short"]), "long": sum(1 for v in found if not v["is_short"])},
            "other_format": [{k: v.get(k) for k in keep[:9]} for v in sorted(other, key=lambda v: v["views_per_day"], reverse=True)[:5]],
            "contact_sheet": "research/trends-contact.jpg" if sheet else None, "thin": len(ranked) < MIN_RESULTS, "unavailable": None}
    if ranked:
        pat = title_patterns([v["title"] for v in ranked])
        data["patterns"] = pat
        data["formulas"] = detect_formulas(ranked)
    save_json(out / "trends.json", data)
    old = (out / "trends.md").read_text(encoding="utf-8") if (out / "trends.md").exists() else ""
    kept = old[old.index(ANALYSIS_HEAD):] if ANALYSIS_HEAD in old else _analysis_template(fmt)
    (out / "trends.md").write_text(render_recent_md(data) + "\n" + kept, encoding="utf-8")
    log(f"wrote research/trends.json, trends.md" + (", trends-contact.jpg" if sheet else "") + f" ({len(ranked)} {fmt} results, {len(found)} found)")
    if data["thin"]:
        warn(f"only {len(ranked)} {fmt} result(s): the gate needs {MIN_RESULTS}. Try another --topic wording, or --unavailable if search is down")
    log("NEXT: open research/trends-contact.jpg, then write the Analysis and `direction` block in research/trends.md; optional: `fishvideo trends <dir> --derive-theme`")
    return data


def mark_unavailable(project, reason: str) -> None:
    project = ensure_project(project)
    if len(reason.strip()) < 8:
        raise SystemExit("trends --unavailable needs the real reason (8+ characters), e.g. 'no network: DNS fails'")
    save_json(project / "research" / "trends.json", {"unavailable": reason.strip(), "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "results": []})
    warn(f"trend research recorded as UNAVAILABLE ({reason.strip()}); built-in themes are the fallback. Say so in the final report.")


def unavailable_reason(project) -> str | None:
    f = Path(project) / "research" / "trends.json"
    if f.exists():
        from fvcore import load_json
        return (load_json(f, default={}) or {}).get("unavailable")
    return None


def analysis_text(project) -> str:
    f = Path(project) / "research" / "trends.md"
    s = f.read_text(encoding="utf-8") if f.exists() else ""
    return s[s.index(ANALYSIS_HEAD) + len(ANALYSIS_HEAD):] if ANALYSIS_HEAD in s else ""


def direction_of(project) -> dict:
    import yaml
    m = re.search(r"```yaml\s*\n(.*?)```", analysis_text(project), re.S)
    try:
        return (yaml.safe_load(m.group(1)) or {}).get("direction") or {} if m else {}
    except Exception:
        return {}


def gate_problems(project, now: dt.datetime | None = None) -> list[str]:
    """Why the gate refuses: no live research, stale, thin, or no written analysis and direction."""
    from fvcore import load_json
    project = Path(project)
    cmd = f"fishvideo trends {project.name}"
    f = project / "research" / "trends.json"
    if not f.exists():
        return [f"trend research missing: run `{cmd}`, open the contact sheet and write the analysis (or `{cmd} --unavailable \"<reason>\"` if search is really down)"]
    d = load_json(f, default={}) or {}
    if d.get("unavailable"):
        return []
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        age = (now - dt.datetime.fromisoformat(d["generated"])).total_seconds() / 86400
    except Exception:
        return [f"trend research unreadable: re-run `{cmd}`"]
    probs = []
    if age > STALE_DAYS:
        probs.append(f"trend research is {age:.0f} days old (limit {STALE_DAYS}): re-run `{cmd}`")
    real = [r for r in d.get("results") or [] if r.get("title") and r.get("url")]
    if len(real) < MIN_RESULTS:
        probs.append(f"trend research has {len(real)} real result(s), needs {MIN_RESULTS}: re-run `{cmd}` with a better --topic, or `{cmd} --unavailable \"<reason>\"` if search is down")
    a = analysis_text(project)
    body = re.sub(r"```.*?```", "", a, flags=re.S)
    if len(body.strip()) < 200 or _TODO.search(body):
        probs.append("trend analysis not written: open research/trends-contact.jpg, then replace every TODO in the Analysis section of research/trends.md with facts from this run (cite #n)")
    dirn = direction_of(project)
    miss = [k for k in DIRECTION_KEYS if not str(dirn.get(k) or "").strip() or _TODO.search(str(dirn.get(k)))]
    if miss:
        probs.append(f"trend direction incomplete ({', '.join(miss)}): fill the `direction:` block in research/trends.md, each citing results (#n)")
    return probs


# ------------------------------------------------------------------ a theme derived from the fetched thumbnails
def _rgb_hsv(c):
    import colorsys
    r, g, b = (x / 255 for x in c)
    return colorsys.rgb_to_hsv(r, g, b)


def _lum(c) -> float:
    def f(x):
        x /= 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def contrast(a, b) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(int(round(x)) for x in c)


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def thumb_palettes(files: list[Path]) -> list[list[tuple]]:
    """Per image: its dominant colours (4-bit bins by pixel share), most common first. Pillow only."""
    from PIL import Image
    out = []
    for f in files:
        try:
            im = Image.open(f).convert("RGB").resize((48, 27))
        except Exception:
            continue
        bins: dict = {}
        for p in im.get_flattened_data() if hasattr(im, 'get_flattened_data') else im.getdata():
            k = (p[0] >> 5, p[1] >> 5, p[2] >> 5)
            n, acc = bins.get(k, (0, (0, 0, 0)))
            bins[k] = (n + 1, tuple(acc[i] + p[i] for i in range(3)))
        out.append([tuple(c / n for c in acc) for n, acc in sorted(bins.values(), key=lambda x: -x[0])[:6]])
    return out


def derive_palette(pals: list[list[tuple]]) -> dict:
    """Pool several thumbnails: keep colours that recur across them, so no single video's look is copied.

    The accent is the most saturated pooled colour; if it sits within 40 RGB units of the leading colour of any one
    source, its hue is turned 40 degrees away so the result is never one channel's look."""
    import colorsys
    if len(pals) < 3:
        raise SystemExit("derive-theme needs thumbnails from at least 3 results; run `fishvideo trends <dir>` first")
    pool = [c for p in pals for c in p]
    def near(a, b):
        return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5
    def support(c):
        return sum(1 for p in pals if any(near(c, x) < 60 for x in p))
    common = [c for c in pool if support(c) >= max(2, len(pals) // 4)] or pool
    lead = [p[0] for p in pals if p]
    dark = sum(1 for c in lead if _lum(c) < 0.18) >= len(lead) / 2     # by what each thumbnail is mostly made of
    sat = sorted(common, key=lambda c: -(_rgb_hsv(c)[1] * (0.4 + _rgb_hsv(c)[2])))
    accent = sat[0]
    if any(near(accent, l) < 40 for l in lead):
        h, s, v = _rgb_hsv(accent)
        accent = tuple(x * 255 for x in colorsys.hsv_to_rgb((h + 40 / 360) % 1, s, v))
    second = next((c for c in sat[1:] if near(c, accent) > 90), _mix(accent, (255, 255, 255), 0.45))
    base = sorted(lead, key=_lum)[len(lead) // 2]
    bg = _mix(base, (8, 8, 10), 0.55) if dark else _mix(base, (250, 248, 242), 0.7)
    ink = (245, 245, 245) if dark else (20, 20, 22)
    for _ in range(20):                                     # contrast checks: text on bg 4.5, accent on bg 3
        if contrast(ink, bg) >= 4.5 and contrast(accent, bg) >= 3.0:
            break
        bg = _mix(bg, (0, 0, 0) if dark else (255, 255, 255), 0.15)
        accent = _mix(accent, (255, 255, 255) if dark else (0, 0, 0), 0.1)
    return {"mode": "dark" if dark else "light", "colors": {"bg": _hex(bg), "ink": _hex(ink), "accent": _hex(accent), "accent2": _hex(second)},
            "contrast": {"ink_on_bg": round(contrast(ink, bg), 2), "accent_on_bg": round(contrast(accent, bg), 2)},
            "min_distance_to_any_source_lead": round(min(near(accent, l) for l in lead), 1) if lead else None}


def derive_theme(project) -> dict:
    """Write research/theme.json: palette from this run's thumbnails + type and texture from the closest built-in theme."""
    import themes
    from fvcore import load_json
    project = Path(project)
    d = load_json(project / "research" / "trends.json", default={}) or {}
    files = [project / "research" / r["thumb_file"] for r in d.get("results") or [] if r.get("thumb_file")]
    files = [f for f in files if f.exists()]
    pal = derive_palette(thumb_palettes(files))
    ths = themes.all_themes()
    def dist(t):
        bgc = t["colors"]["bg"].lstrip("#")
        a = tuple(int(bgc[i:i + 2], 16) for i in (0, 2, 4))
        b = tuple(int(pal["colors"]["bg"][i:i + 2], 16) for i in (1, 3, 5))
        return (0 if t.get("mode") == pal["mode"] else 1000) + sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5
    base = min(ths, key=lambda k: dist(ths[k]))
    out = {"id": "derived", "base": base, "mode": pal["mode"], "colors": pal["colors"], "contrast": pal["contrast"],
           "from_results": len(files), "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "note": "palette pooled from several thumbnails of this run; type, texture and layout come from the built-in theme `" + base + "`"}
    save_json(project / "research" / "theme.json", out)
    log(f"derived theme: base {base}, {pal['mode']}, colours {pal['colors']}, contrast {pal['contrast']} -> research/theme.json")
    return out


def derived_theme(project) -> dict | None:
    f = Path(project) / "research" / "theme.json"
    if f.exists():
        from fvcore import load_json
        return load_json(f, default=None)
    return None


# ------------------------------------------------------------------ sounds in trending videos (analysis only, never downloaded)
STYLE_WORDS = ["lofi", "lo-fi", "phonk", "cinematic", "orchestral", "ambient", "dark", "epic", "trap", "hip hop", "synthwave", "piano", "acoustic",
               "upbeat", "chill", "drill", "house", "edm", "horror", "suspense", "emotional", "sad", "funny", "meme", "viral sound", "slowed", "sped up", "remix"]
_SOUND_LINE = re.compile(r"(?im)^\W*(?:music|song|track|audio|sound|soundtrack|beat|instrumental)\s*[:\-\u2013]\s*(.{3,120})$")
_NOTE_LINE = re.compile(r"[\u266a\u266b\U0001F3B5\U0001F3B6]\s*([^\n#]{3,100})")


def find_sounds(rec: dict) -> list[dict]:
    """Sound or music mentions in one video's metadata. Only what the data states; nothing is guessed."""
    out = []
    if rec.get("track"):
        out.append({"sound": f"{rec['track']}" + (f" - {rec['artist']}" if rec.get("artist") else ""), "via": "platform music metadata"})
    blob = {"title": rec.get("title") or "", "description": rec.get("description") or "", "tags": " \n".join(rec.get("tags") or [])}
    for where, text in blob.items():
        if re.search(r"original sound|original audio", text, re.I):
            out.append({"sound": "original sound", "via": where})
        for m in _SOUND_LINE.finditer(text):
            out.append({"sound": m.group(1).strip(), "via": where})
        for m in _NOTE_LINE.finditer(text):
            out.append({"sound": m.group(1).strip(), "via": where})
    seen, uniq = set(), []
    for o in out:
        k = o["sound"].lower()
        if k not in seen:
            seen.add(k)
            uniq.append(o)
    return uniq


def sounds(project, top: int = 8) -> dict:
    """`trends --sounds`: sounds and music named in the trend results' metadata, and the common style words.
    Writes research/trend-sounds.json and trend-sounds.md. The licensed route to a trending sound is YouTube's own Shorts editor."""
    project = ensure_project(project)
    src = project / "research" / "trends.json"
    if not src.exists():
        raise SystemExit("trends --sounds: run `fishvideo trends <dir>` first (it needs the live results)")
    from fvcore import load_json
    data = load_json(src)
    rows = (data.get("results") or [])[:top]
    seen, styles, errs = [], Counter(), 0
    for r in rows:
        try:
            full = youtube.info(r["url"])
        except Exception as e:                                       # noqa: BLE001 - one video failing must not stop the rest
            errs += 1
            full = {"title": r.get("title"), "tags": []}
            warn(f"sounds: {r.get('url')}: {str(e)[:80]}")
        found = find_sounds(full)
        text = " ".join([full.get("title") or "", " ".join(full.get("tags") or []), (full.get("description") or "")[:600]]).lower()
        for w in STYLE_WORDS:
            if w in text:
                styles[w] += 1
        seen.append({"title": r.get("title"), "url": r.get("url"), "sounds": found})
    named = sum(1 for s in seen if s["sounds"])
    res = {"topic": data.get("topic"), "checked": len(seen), "with_named_sound": named, "fetch_errors": errs,
           "styles": styles.most_common(6), "videos": seen, "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    out = project / "research"
    save_json(out / "trend-sounds.json", res)
    L = [f"# Sounds in trending videos: {data.get('topic')}", "",
         f"Checked the metadata (title, description, tags, platform music fields) of the top {len(seen)} results in research/trends.json. "
         f"{named} of them name a sound or track." + ("" if named else " The data does not expose it: YouTube's public metadata does not list the sound used in a Short unless the creator wrote it in the description."), ""]
    for s in seen:
        L.append(f"- {s['title']} ({s['url']}): " + (", ".join(f"{x['sound']} [{x['via']}]" for x in s["sounds"]) if s["sounds"] else "no sound named in the data"))
    L += ["", "Common style words in titles, tags and descriptions: " + (", ".join(f"{w} ({n})" for w, n in res["styles"]) if res["styles"] else "none found"),
          "Tempo and key are not in the data; they are not estimated here.", "",
          "Rights: popular tracks and viral sounds are copyrighted, so this tool never downloads or embeds them. To use a trending sound legally, "
          "attach it in YouTube's own Shorts editor when you upload (Add sound). For a licensed track inside the video, run `fishvideo music source <dir>` "
          "(CC0 and CC BY only); otherwise the synthesised score is used.", ""]
    (out / "trend-sounds.md").write_text("\n".join(L), encoding="utf-8")
    log(f"wrote research/trend-sounds.md ({named}/{len(seen)} videos name a sound; styles: {res['styles'][:3]})")
    return res


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="trends.py", description=__doc__.split("\n")[0])
    ap.add_argument("project")
    ap.add_argument("--topic")
    ap.add_argument("--format", choices=["shorts", "long"])
    ap.add_argument("--region", default="US")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("-n", type=int, default=30)
    ap.add_argument("--no-hooks", action="store_true")
    ap.add_argument("--legacy", action="store_true", help="the older all-in-one report (needs --topic)")
    ap.add_argument("--derive-theme", action="store_true")
    ap.add_argument("--unavailable", metavar="REASON")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sounds", action="store_true", help="list sounds/music named in the trend results, write research/trend-sounds.md")
    ns = ap.parse_args(argv)
    if ns.sounds:
        sounds(Path(ns.project))
    elif ns.unavailable:
        mark_unavailable(Path(ns.project), ns.unavailable)
    elif ns.derive_theme:
        derive_theme(Path(ns.project))
    elif ns.check:
        pr = gate_problems(Path(ns.project))
        for p in pr:
            warn(p)
        log("trend research: ok" if not pr else f"trend research: {len(pr)} problem(s)")
        return 1 if pr else 0
    elif ns.legacy:
        trends(Path(ns.project), ns.topic or "", ns.region, ns.days, ns.n, hooks=not ns.no_hooks)
    else:
        recent(Path(ns.project), ns.topic, ns.format, ns.days, ns.n)
    return 0


if __name__ == "__main__":
    main_guard(cli)
