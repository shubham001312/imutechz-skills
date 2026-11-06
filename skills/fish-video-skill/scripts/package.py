"""Package: one tidy, upload-ready folder per video.

    python scripts/package.py <project> [--out "<project>/out"] [--name "Project 2"]

<out>/<YYYY-MM-DD>_<slug>/
    README.md                     index: what each file is, durations, QA status, what to upload where
    video/<slug>-<platform>.mp4   one encoded cut per platform
    captions/<slug>-<platform>.srt|.vtt
    thumbnails/thumbnail-1280x720.png      YouTube thumbnail (the one `fishvideo thumb pick` chose, else the storyboard's thumbnail scene),
                                           with thumbnail-variants.png, thumbnail-feed-*.png and thumbnail-check.md when `thumb make` was run
    thumbnails/cover-<platform>.png        a vertical cover frame per 9:16 / 4:5 cut
    metadata/titles.txt           title options (brief.publish.titles, informed by research/trends.md)
    metadata/<platform>-post.txt  title, description with chapters, sources, hashtags, credits
    metadata/tags.txt             <= 15 tags
    metadata/transcript.txt       the narration as captioned
    metadata/credits.txt          every third-party asset with licence + attribution, music, voice, AI disclosure
    metadata/metadata.json        everything above, machine readable
    qa/qa.md, qa/contact-<platform>.png
Nothing is uploaded or published.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from pathlib import Path

from fvcore import SKILL, FishError, ensure_project, load_json, log, main_guard, mmss, node, project_config, slugify
import fvnet
import storyboard as sbmod


def chapters(tl: dict) -> list[tuple[str, str]]:
    out = [("0:00", "Intro")]
    for s in tl["scenes"]:
        if s.get("chapter") and s["t0"] > 0:
            out.append((mmss(s["t0"]), re.sub(r"^\d+\s*·\s*", "", s["chapter"])))
    # YouTube needs >= 3 chapters of >= 10 s, starting at 0:00
    ok = len(out) >= 3 and all(_sec(b) - _sec(a) >= 10 for (a, _), (b, _) in zip(out, out[1:]))
    return out if ok else []


def _sec(m: str) -> int:
    a, b = m.split(":")
    return int(a) * 60 + int(b)


def fill(template: str, ctx: dict) -> str:
    out = template
    for k, v in ctx.items():
        out = out.replace("{{" + k + "}}", str(v))
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"\{\{\w+\}\}", "", out)).strip() + "\n"


def tags_for(brief: dict, trends: dict | None = None) -> list[str]:
    tags = [str(t).lstrip("#") for t in (brief.get("publish") or {}).get("tags") or brief.get("hashtags") or []]
    for t in (trends or {}).get("recommended_tags") or []:
        if str(t).lower() not in [x.lower() for x in tags]:
            tags.append(str(t))
    if (brief.get("publish") or {}).get("tags"):
        return tags[:15]      # the writer chose them: don't pad with words from the title
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", " ".join([brief.get("title", ""), (brief.get("brand") or {}).get("name", "") or "", *map(str, brief.get("points") or [])]))
    stop = {"the", "and", "for", "with", "your", "you", "that", "this", "how", "what", "from", "into", "are", "its", "our", "todo"}
    for w in words:
        if w.lower() not in stop and w.lower() not in [t.lower() for t in tags]:
            tags.append(w)
    return tags[:15]


def credits_text(project: Path, voice: dict, music_note: str) -> str:
    lines = ["CREDITS"]
    cf = project / "assets" / "credits.json"
    items = load_json(cf, default=[]) if cf.exists() else []
    if isinstance(items, dict):
        items = items.get("items") or list(items.values())
    held: dict[str, list[str]] = {"platform": [], "unverified": []}
    for it in items:
        if not isinstance(it, dict):
            continue
        att = it.get("attribution") or f"\"{it.get('title') or it.get('id')}\" by {it.get('author') or 'unknown'} ({it.get('provider')})"
        line = f"- {att}, licence: {it.get('license')}" + (f" {it.get('license_url')}" if it.get("license_url") else "") + (f" {it.get('url')}" if it.get("url") else "")
        tier = fvnet.risk_of(it)
        if tier == "safe":
            if line not in lines:
                lines.append(line)
        elif line not in held[tier]:
            held[tier].append(line)
    for tier, head in (("platform", "Shown under the source's own terms (no open licence):"),
                       ("unverified", "LICENCE NOT VERIFIED (review before publishing; these can be claimed, muted or taken down):")):
        if held[tier]:
            lines += ["", head] + held[tier] + [""]
    lines.append(f"- Music: {music_note}")
    prov = voice.get("provider")
    if prov and prov != "none":
        who = voice.get("voice") or voice.get("voice_id")
        lines.append(f"- Voice: AI narration ({prov}{', ' + str(who) if who else ''}).")
        lines.append("- Disclosure: this video uses an AI-generated voice and AI-assisted editing.")
    return "\n".join(lines)


def package_slug(brief: dict) -> str:
    """The file/folder slug follows the CURRENT brief.title, so renaming the title renames the package.
    (A slug saved at brief creation went stale: it kept the first words of the prompt.) Use `package_name` to pin a folder name."""
    return slugify(brief.get("title") or brief.get("slug") or "video")


def package(project: Path, out: Path | None = None, name: str | None = None) -> Path:
    project = ensure_project(project)
    cfg = project_config(project)
    brief = cfg["brief"]
    slug = package_slug(brief)
    folder = name or brief.get("package_name") or f"{time.strftime('%Y-%m-%d')}_{slug}"
    dest = Path(out or project / "out") / folder
    for sub in ("video", "captions", "thumbnails", "metadata", "qa"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    plats = sbmod.platforms_of(cfg)
    rs = project / "research" / "sources.json"
    sources = load_json(rs, default={"sources": []}).get("sources", []) if rs.exists() else []
    tj = project / "research" / "trends.json"
    trends = load_json(tj, default={}) if tj.exists() else {}
    cj = project / "build" / "voice" / "clips.json"
    clips = load_json(cj, default={}) if cj.exists() else {}
    voice = clips.get("voice") or {"provider": clips.get("provider", "none")}
    mdir = project / "assets" / "music"
    track = next((f for f in sorted(mdir.glob("*")) if f.is_file()), None) if mdir.exists() else None
    music_note = f"\"{track.stem}\" (licence in the credits above)" if track and (brief.get("music") or {}).get("source") != "synth" else "original score, synthesised for this video"
    credits = credits_text(project, voice, music_note)
    pub = brief.get("publish") or {}
    titles = pub.get("titles") or [brief.get("title", "")]
    meta = {"title": titles[0], "titles": titles, "slug": slug, "style": brief.get("style"), "language": brief.get("language"), "voice": voice,
            "music": music_note, "sources": [{"id": s["id"], "url": s["url"], "title": s.get("title")} for s in sources],
            "facts": brief.get("facts") or [], "cuts": [], "created": time.strftime("%Y-%m-%d %H:%M")}
    tpl = (SKILL / "templates" / "description.md").read_text(encoding="utf-8")
    transcript = None
    rows = []
    for p in plats:
        b = project / "build" / p
        final = b / "final.mp4"
        if not final.exists():
            raise FishError(f"{final} missing: render {p} first")
        tl = load_json(project / "build" / f"timeline-{p}.json")
        vid = dest / "video" / f"{slug}-{p}.mp4"
        shutil.copy2(final, vid)
        for ext in ("srt", "vtt"):
            if (b / f"captions.{ext}").exists():
                shutil.copy2(b / f"captions.{ext}", dest / "captions" / f"{slug}-{p}.{ext}")
        if (b / "contact.png").exists():
            shutil.copy2(b / "contact.png", dest / "qa" / f"contact-{p}.png")
        if transcript is None and tl.get("voice_lines"):
            transcript = "\n".join(v["display"] for v in tl["voice_lines"])
        chs = chapters(tl) if p in ("youtube", "x") else []
        qj = b / "qa.json"
        qa = load_json(qj, default={}) if qj.exists() else {}
        ctx = {
            "title": titles[0], "summary": pub.get("description") or brief.get("summary") or (brief.get("brand") or {}).get("tagline") or brief.get("prompt", ""),
            "points": "\n".join(f"- {x}" for x in brief.get("points") or []),
            "chapters": ("CHAPTERS\n" + "\n".join(f"{a} {t}" for a, t in chs)) if chs else "",
            "links": "\n".join(x for x in [((brief.get("brand") or {}).get("url") or ""), (brief.get("cta") or {}).get("url", "")] if x),
            "cta": (brief.get("cta") or {}).get("text", ""),
            "sources": ("SOURCES\n" + "\n".join(f"[{s['id']}] {s['url']}" for s in sources)) if sources else "",
            "hashtags": " ".join("#" + str(t).lstrip("#") for t in (pub.get("hashtags") or brief.get("hashtags") or [])),
            "credits": credits, "platform": tl.get("label", p), "duration": mmss(tl["duration"]),
        }
        (dest / "metadata" / f"{p}-post.txt").write_text(fill(tpl, ctx), encoding="utf-8")
        if tl["H"] > tl["W"]:
            node("stills.mjs", project, "--platform", p, "--at", str(pub.get("cover_at", 0.6)), "--out", dest / "thumbnails" / f"cover-{p}.png", capture=True, check=False)
        meta["cuts"].append({"platform": p, "file": f"video/{vid.name}", "duration": tl["duration"], "W": tl["W"], "H": tl["H"],
                             "captions_burned": tl["captions"]["burn"], "qa": qa.get("status"), "checks": {c["check"]: c["detail"] for c in qa.get("checks", [])}})
        rows.append(f"| {tl.get('label', p)} | video/{vid.name} | {mmss(tl['duration'])} | {tl['W']}x{tl['H']} | {qa.get('status', '?')} |")
    md = dest / "metadata"
    if transcript:
        (md / "transcript.txt").write_text(transcript + "\n", encoding="utf-8")
    thumb = dest / "thumbnails" / "thumbnail-1280x720.png"
    r = node("stills.mjs", project, "--platform", "thumbnail", "--at", "0.5", "--out", thumb, capture=True, check=False)
    if not thumb.exists():
        log(f"!! thumbnail failed: {(r.stderr or '')[-300:]}")
    import thumbs
    for name in thumbs.ship(project, dest):      # the picked thumbnail, the variants and feed sheets, the check results
        log(f"  thumbnails: {name}")
    from PIL import Image
    import numpy as np
    shots = []
    for f in sorted((dest / "thumbnails").glob("*.png")):
        try:
            with Image.open(f) as im:
                if thumbs.looks_like_screenshot(np.asarray(im.convert("RGB"))):
                    shots.append(f.name)
        except OSError:
            pass
    if shots:
        raise FishError("a thumbnail or cover is a website screenshot (" + ", ".join(shots) + "). Make a designed one: set thumbnail.logos in storyboard.yaml, "
                        "run `fishvideo thumb make <dir>` (logos layout) and `fishvideo thumb pick <dir> N`, then package again.")
    tags = tags_for(brief, trends)
    (md / "tags.txt").write_text(", ".join(tags) + "\n", encoding="utf-8")
    (md / "titles.txt").write_text("\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles)) + "\n", encoding="utf-8")
    (md / "credits.txt").write_text(credits + "\n", encoding="utf-8")
    meta["tags"] = tags
    if (project / "build" / "qa.md").exists():
        shutil.copy2(project / "build" / "qa.md", dest / "qa" / "qa.md")
    (md / "metadata.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    readme = [f"# {titles[0]}", "", f"Style: {brief.get('style') or '-'} · Voice: {voice.get('provider')} · Created {meta['created']}", "",
              "| Cut | File | Length | Size | QA |", "|---|---|---|---|---|", *rows, "",
              "## Upload checklist", "",
              "- YouTube 16:9: the video, `captions/*-youtube.srt` as subtitles, `thumbnails/thumbnail-1280x720.png`, and the text of `metadata/youtube-post.txt`.",
              "- Shorts / Reels / TikTok: the 9:16 video (captions are burned in), a cover from `thumbnails/cover-*.png`, and `metadata/<platform>-post.txt`.",
              "- Tags: `metadata/tags.txt`. Title options: `metadata/titles.txt`. The credits are already in each post text.",
              "", "Nothing here has been uploaded."]
    (dest / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    log(f"package: {dest}")
    for f in sorted(dest.rglob("*")):
        if f.is_file():
            log(f"  {str(f.relative_to(dest)):<52} {f.stat().st_size / 1e6:8.2f} MB")
    return dest


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--out", default=None)
    ap.add_argument("--name", default=None)
    a = ap.parse_args(argv)
    package(Path(a.project), Path(a.out) if a.out else None, a.name)
    return 0


if __name__ == "__main__":
    main_guard(cli)
