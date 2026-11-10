"""Logos, icons and emoji as clean SVG files, each with its licence.

    python scripts/assets.py logo  <project> "hugging face" [--color brand|white|black|#hex]
    python scripts/assets.py icon  <project> rocket                 list matching icons from open-licence sets
    python scripts/assets.py icon  <project> mdi:rocket [--color #f2b722]   download one
    python scripts/assets.py emoji <project> 😂 | "FACE WITH TEARS OF JOY" [--set openmoji|twemoji]

Sources (all key-less): Simple Icons (brand marks), Iconify (open icon sets; only sets whose licence
allows commercial use), OpenMoji and Twemoji. Every file is sanitised (fvnet.sanitize_svg) before it is
saved under assets/icons/, because the stage loads it in a browser, and it is logged in assets/credits.json.
A logo's file may be CC0 while the mark itself is still someone's trademark: follow the brand's guidelines.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from fvcore import FishError, ensure_project, log, warn
import fvnet
from fvnet import add_credit

SI = "https://cdn.jsdelivr.net/npm/simple-icons@latest"
ICONIFY = "https://api.iconify.design"
# SPDX ids of icon-set licences that allow commercial use (attribution where the licence asks for it)
OPEN_SPDX = {"MIT", "Apache-2.0", "ISC", "CC0-1.0", "CC-BY-4.0", "CC-BY-3.0", "CC-BY-SA-4.0", "CC-BY-SA-3.0", "OFL-1.1", "Unlicense",
             "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0", "0BSD"}
NEEDS_CREDIT = {"CC-BY-4.0", "CC-BY-3.0", "CC-BY-SA-4.0", "CC-BY-SA-3.0"}
EMOJI_SETS = {
    "openmoji": {"url": "https://cdn.jsdelivr.net/npm/openmoji@latest/color/svg/{code}.svg", "upper": True, "license": "CC BY-SA 4.0",
                 "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "author": "OpenMoji (openmoji.org)", "home": "https://openmoji.org/"},
    "twemoji": {"url": "https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/assets/svg/{code}.svg", "upper": False, "license": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/", "author": "Twitter, Inc. and other contributors (Twemoji)", "home": "https://github.com/jdecked/twemoji"},
}
HEX = re.compile(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def _color(value: str | None, brand_hex: str | None = None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    if v == "brand":
        return f"#{brand_hex}" if brand_hex else None
    if v in ("white", "black"):
        return {"white": "#ffffff", "black": "#000000"}[v]
    m = HEX.match(value.strip())
    if not m:
        raise FishError(f"colour '{value}' must be brand, white, black or a hex code like #f2b722")
    return "#" + m.group(1)


def _tint(svg: str, color: str | None) -> str:
    """Set the fill on the root <svg>, for single-colour marks (paths inherit it)."""
    if not color:
        return svg
    head, rest = svg.split(">", 1)
    head = re.sub(r'\sfill="[^"]*"', "", head)
    return f'{head} fill="{color}">{rest}'


def _save(project: Path, name: str, svg: str) -> Path:
    dest = project / "assets" / "icons" / f"{fvnet.safe_name(name)}.svg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(fvnet.sanitize_svg(svg), encoding="utf-8")
    return dest


def _credit(project: Path, dest: Path, **rec) -> None:
    rec["file"] = str(dest.relative_to(project)).replace("\\", "/")
    rec.setdefault("kind", "icon")
    add_credit(project, rec)


# ------------------------------------------------------------------ brand logos (Simple Icons)
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def find_brand(brand: str, data: list[dict]) -> dict | None:
    """The Simple Icons entry for a brand: by slug, title, then alias; then a title that starts with the query."""
    want = _norm(brand)
    names = lambda e: [e.get("slug", ""), e.get("title", "")] + list(((e.get("aliases") or {}).get("aka") or [])) + list(((e.get("aliases") or {}).get("old") or []))
    for e in data:
        if want in {_norm(x) for x in names(e)}:
            return e
    # a title that merely starts with the query is a DIFFERENT brand unless the rest is a generic suffix ("openai" must not give "OpenAI Gym")
    generic = {"js", "app", "apps", "logo", "inc", "com", "io", "cloud", "ai"}
    return next((e for e in data if _norm(e.get("title", "")).startswith(want) and _norm(e["title"])[len(want):] in generic), None) if len(want) >= 3 else None


def logo(project, brand: str, color: str | None = "brand") -> Path:
    project = ensure_project(project)
    data = fvnet.fetch_json(f"{SI}/data/simple-icons.json")
    data = data.get("icons", data) if isinstance(data, dict) else data
    e = find_brand(brand, data)
    if not e:
        raise FishError(f"no Simple Icons mark for '{brand}'. Some brands asked to be removed; use the brand's own press kit (and its terms) instead.")
    slug = e.get("slug") or _norm(e["title"])
    svg = fvnet.fetch(f"{SI}/icons/{fvnet.safe_name(slug)}.svg").decode("utf-8", "replace")
    dest = _save(project, f"logo-{slug}", _tint(svg, _color(color, e.get("hex"))))
    lic = (e.get("license") or {}).get("type") or "CC0-1.0"
    open_file = lic in OPEN_SPDX
    _credit(project, dest, id=f"simpleicons-{slug}", provider="simpleicons", title=f"{e['title']} logo", url=e.get("source") or "https://simpleicons.org/",
            author=e["title"], license=lic if open_file else f"{lic} (see the source)", license_url=(e.get("license") or {}).get("url") or "https://github.com/simple-icons/simple-icons/blob/develop/LICENSE.md",
            attribution_required=lic in NEEDS_CREDIT, risk="safe" if open_file else "platform",
            trademark=f"{e['title']} is a trademark of its owner; follow its brand guidelines" + (f": {e['guidelines']}" if e.get("guidelines") else "."), brand_hex=e.get("hex"))
    log(f"logo {e['title']} -> {dest.relative_to(project)}  [{lic}; trademark of its owner]")
    return dest


# ------------------------------------------------------------------ icons (Iconify)
def icon_search(q: str, n: int = 12) -> list[dict]:
    """Icons from sets whose licence is open: [{id, set, name, license, spdx, author, license_url}]."""
    d = fvnet.fetch_json(f"{ICONIFY}/search", {"query": q, "limit": max(32, min(n * 4, 96))})
    sets = d.get("collections") or {}
    out = []
    for full in d.get("icons") or []:
        prefix, _, name = full.partition(":")
        info = sets.get(prefix) or {}
        lic = info.get("license") or {}
        if lic.get("spdx") not in OPEN_SPDX:
            continue
        out.append({"id": full, "set": info.get("name") or prefix, "name": name, "license": lic.get("title") or lic.get("spdx"), "spdx": lic.get("spdx"),
                    "license_url": lic.get("url") or "", "author": (info.get("author") or {}).get("name") or prefix})
        if len(out) >= n:
            break
    return out


def icon(project, q: str, color: str | None = None, n: int = 12):
    """`set:name` downloads that icon; anything else lists matches."""
    project = ensure_project(project)
    if not re.fullmatch(r"[a-z0-9-]+:[a-z0-9-]+", q):
        res = icon_search(q, n)
        log(f"{len(res)} icons from open-licence sets (download one with: assets icon <project> <id>)")
        for r in res:
            log(f"  {r['id']:<40} {r['spdx']:<14} {r['set']}")
        return res
    prefix, name = q.split(":")
    info = (fvnet.fetch_json(f"{ICONIFY}/collections", {"prefixes": prefix}) or {}).get(prefix) or {}
    lic = info.get("license") or {}
    if lic.get("spdx") not in OPEN_SPDX:
        raise FishError(f"the icon set '{prefix}' has licence '{lic.get('spdx') or 'unknown'}', which is not on the open list: choose another set")
    svg = fvnet.fetch(f"{ICONIFY}/{prefix}/{name}.svg", {"color": _color(color), "height": 512}).decode("utf-8", "replace")
    dest = _save(project, f"icon-{prefix}-{name}", svg)
    _credit(project, dest, id=f"iconify-{prefix}-{name}", provider="iconify", title=f"{name} ({info.get('name') or prefix})", url=f"https://icon-sets.iconify.design/{prefix}/?icon-filter={name}",
            author=(info.get("author") or {}).get("name") or prefix, license=lic.get("title") or lic["spdx"], license_url=lic.get("url") or "",
            attribution_required=lic["spdx"] in NEEDS_CREDIT, risk="safe")
    log(f"icon {q} -> {dest.relative_to(project)}  [{lic['spdx']}]")
    return dest


# ------------------------------------------------------------------ emoji
def emoji_codes(text: str) -> list[int]:
    """Code points of an emoji given as the character(s) or as its Unicode name ("FACE WITH TEARS OF JOY")."""
    t = text.strip()
    if not t:
        raise FishError("give an emoji or its Unicode name")
    if t.isascii():
        try:
            return [ord(unicodedata.lookup(t.upper()))]
        except KeyError:
            raise FishError(f"'{text}' is not a Unicode character name. Paste the emoji itself, or use a name like FACE WITH TEARS OF JOY.")
    return [ord(ch) for ch in t]


def emoji(project, text: str, eset: str = "openmoji") -> Path:
    project = ensure_project(project)
    if eset not in EMOJI_SETS:
        raise FishError(f"emoji set must be one of {sorted(EMOJI_SETS)}")
    cfg = EMOJI_SETS[eset]
    cps = emoji_codes(text)
    # the sets differ on the variation selector U+FE0F: try the sequence as given, then without it
    tries = [cps] + ([[c for c in cps if c != 0xFE0F]] if 0xFE0F in cps else [])
    svg, code = None, ""
    for seq in tries:
        code = "-".join(f"{c:X}" if cfg["upper"] else f"{c:x}" for c in seq)
        try:
            svg = fvnet.fetch(cfg["url"].format(code=code)).decode("utf-8", "replace")
            break
        except fvnet.NetError:
            continue
    if svg is None:
        raise FishError(f"{eset} has no file for '{text}' ({code}); try --set {'twemoji' if eset == 'openmoji' else 'openmoji'}")
    dest = _save(project, f"emoji-{eset}-{code.lower()}", svg)
    try:
        title = unicodedata.name(chr(cps[0])).title()
    except ValueError:
        title = f"emoji {code}"
    _credit(project, dest, id=f"{eset}-{code.lower()}", provider=eset, title=title, url=cfg["home"], author=cfg["author"], license=cfg["license"],
            license_url=cfg["license_url"], attribution_required=True, risk="safe")
    log(f"emoji {title} -> {dest.relative_to(project)}  [{cfg['license']}]")
    return dest
