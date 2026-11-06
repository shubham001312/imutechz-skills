"""Turn a one-line prompt into a project brief, and create the project folder.

    python scripts/brief.py "A 45 s LinkedIn promo for https://example.com in Hindi" --out projects/demo

`parse_prompt` is deliberately conservative: it extracts only what the
prompt states (length, platforms, links, a reference video, language,
structure hints) and leaves everything else to the defaults and to the
agent, who should then edit brief.yaml. It never invents facts.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from fvcore import SKILL, FishError, deep_merge, load_yaml, log, main_guard, save_yaml, slugify

PLATFORM_WORDS = [
    (r"\byou ?tube shorts?\b|\bshorts\b", "shorts"),
    (r"\breels?\b|\binstagram\b", "reels"),
    (r"\btik ?tok\b", "tiktok"),
    (r"\blinked ?in\b.*\b(square|1:1)\b|\b(square|1:1)\b.*\blinked ?in\b", "linkedin-square"),
    (r"\blinked ?in\b", "linkedin"),
    (r"\byou ?tube\b(?! shorts)", "youtube"),
    (r"\btwitter\b|\bx\.com\b|\bon x\b|\bfor x\b", "x"),
    (r"\bvertical\b|\b9:16\b", "shorts"),
    (r"\b4:5\b", "linkedin"),
    (r"\b16:9\b|\blandscape\b", "youtube"),
]
LANGS = [
    (r"\bhindi\b|\bhi-in\b", "hi-IN"), (r"\bindian english\b|\ben-in\b|\benglish \(india\)", "en-IN"),
    (r"\bbritish\b|\ben-gb\b", "en-GB"), (r"\bamerican\b|\ben-us\b", "en-US"), (r"\bspanish\b|\bes-es\b", "es-ES"),
    (r"\bfrench\b|\bfr-fr\b", "fr-FR"), (r"\bgerman\b|\bde-de\b", "de-DE"), (r"\btamil\b", "ta-IN"), (r"\bbengali\b", "bn-IN"),
]
STRUCTURES = [
    (r"\btour\b|\bwalk ?through\b|\bdemo\b", "product-tour"),
    (r"\bhow (it|does|do)\b|\bexplain|\bexplainer\b|\bunder the hood\b", "explainer"),
    (r"\btop \d+\b|\blist\b|\breasons\b|\btips\b", "listicle"),
    (r"\blaunch|\bannounc|\bintroducing\b|\brelease\b", "announcement"),
    (r"\bstory\b|\bjourney\b", "story"),
    (r"\bpromo\b|\bad\b|\badvert|\bteaser\b", "promo"),
]
URL = re.compile(r"https?://[^\s,)\"'>]+", re.I)
YT = re.compile(r"(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)", re.I)
VIDEO_FILE = re.compile(r"(?:(?<=\s)|^)([A-Za-z]:[\\/][^\s\"']+|[./~][^\s\"']*)\.(mp4|mov|mkv|webm|m4v)\b", re.I)


def parse_length(text: str) -> float | None:
    """'90 second', '2 min', '1:30', '45s' -> seconds."""
    t = text.lower()
    m = re.search(r"\b(\d{1,2}):(\d{2})\b(?!\s*(?:am|pm))", t)
    if m and not re.search(r"\d:\d{2}\s*(aspect|ratio)", t):
        mins, secs = int(m.group(1)), int(m.group(2))
        if mins < 20 and not (mins in (1, 4, 9, 16) and secs in (1, 5, 9, 16)):
            return float(mins * 60 + secs)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|\s)?(minutes?|mins?|m)\b(?!b)", t)
    if m:
        return float(m.group(1)) * 60
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|\s)?(seconds?|secs?|s)\b", t)
    if m:
        return float(m.group(1))
    return None


def parse_prompt(prompt: str) -> dict:
    """Extract the facts a prompt states. Returns a partial brief."""
    p = " " + prompt.strip() + " "
    low = p.lower()
    out: dict = {"prompt": prompt.strip()}
    urls = [u.rstrip(".") for u in URL.findall(p)]
    ref = next((u for u in urls if YT.search(u)), None)
    vf = VIDEO_FILE.search(p)
    if ref or vf:
        out["reference"] = {"src": ref or (vf.group(1) + "." + vf.group(2))}
    sites = [u for u in urls if u != ref]
    if sites:
        out["website"] = {"url": sites[0], "pages": []}
        out["sources"] = sites
    found: list[tuple[int, str]] = []
    for rx, name in PLATFORM_WORDS:
        m = re.search(rx, low)
        if m and name not in [n for _, n in found]:
            if name == "linkedin" and any(n == "linkedin-square" for _, n in found):
                continue
            found.append((m.start(), name))
    plats = [n for _, n in sorted(found)]  # in the order the prompt names them: the first is the master cut
    if plats:
        out["platforms"] = plats
    length = parse_length(low)
    if length:
        out["length"] = length
    for rx, lang in LANGS:
        if re.search(rx, low):
            out["language"] = lang
            break
    for rx, st in STRUCTURES:
        if re.search(rx, low):
            out["structure"] = "product-tour" if st == "explainer" and sites and "tour" in low else st
            break
    if "structure" not in out:
        out["structure"] = "product-tour" if sites else "explainer"
    if re.search(r"\bno (voice|narration|voiceover)\b|\bmusic only\b|\bsilent\b", low):
        out["voice"] = {"provider": "none"}
    if re.search(r"\bdark (mode|theme)\b", low):
        out.setdefault("brand", {})["mode"] = "dark"
    m = re.search(r"#([0-9a-f]{6})\b", low)
    if m:
        out.setdefault("brand", {}).setdefault("colors", {})["accent"] = "#" + m.group(1)
    # a title: the quoted phrase, else the subject after "about"/"for"/"of"
    q = re.search(r"[\"“']([^\"”']{3,80})[\"”']", prompt)
    if q:
        out["title"] = q.group(1).strip()
    else:
        m = re.search(r"\b(?:about|explaining|introducing|on|of)\s+([^,.;]+)", prompt, re.I)
        if m:
            subj = URL.sub("", m.group(1))
            subj = re.split(r"\b(for|in|with|on|at|using|under|as)\b", subj, flags=re.I)[0].strip(" -:")
            if subj and norm_words(subj) - FILLER_TITLE_WORDS:
                out["title"] = subj[:80]
    return out


FILLER_TITLE_WORDS_SRC = "this that it its these those them they the a an my our your his her their one some any"
FILLER_TITLE_WORDS = set(FILLER_TITLE_WORDS_SRC.split())


def norm_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def make_brief(prompt: str = "", **over) -> dict:
    """Template brief + prompt facts + explicit overrides (in that order)."""
    tpl = load_yaml(SKILL / "templates" / "brief.yaml")
    b = deep_merge(tpl, parse_prompt(prompt) if prompt else {})
    b = deep_merge(b, {k: v for k, v in over.items() if v not in (None, "", [], {})})
    if not b.get("title"):
        b["title"] = (b.get("brand") or {}).get("name") or "Untitled video"
    return b


def new_project(out: Path | str, prompt: str = "", force: bool = False, **over) -> Path:
    """Create <out>/ with brief.yaml (and the standard sub-folders)."""
    from fvcore import norm_path
    out = norm_path(out).resolve()
    if (out / "brief.yaml").exists() and not force:
        raise FishError(f"{out / 'brief.yaml'} exists (use --force to overwrite)")
    b = make_brief(prompt, **over)
    for d in ("assets", "research", "reference", "build", "out"):
        (out / d).mkdir(parents=True, exist_ok=True)
    save_yaml(out / "brief.yaml", b)
    (out / ".gitignore").write_text("build/\n.env\nreference/src.*\nresearch/trend-thumbs/\nresearch/trends-contact.jpg\nresearch/trends.json\n", encoding="utf-8")
    log(f"new project: {out}  ({b['structure']}, {b.get('length')} s, {', '.join(b['platforms'])}, {b.get('language')})")
    return out


def cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompt", nargs="?", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    new_project(a.out, a.prompt, force=a.force)
    return 0


if __name__ == "__main__":
    main_guard(cli)
