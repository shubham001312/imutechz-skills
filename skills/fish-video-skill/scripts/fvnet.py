"""Small shared network + credits helpers for the research / asset tools.

stdlib only (urllib). Every request sends a descriptive User-Agent, times out
at 20 s and raises NetError (a FishError) with a clear message, so callers can
fail soft. Also hosts the assets/credits.json ledger used by youtube.py and
assets.py (one record per (provider, id), deduped).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from fvcore import FishError, load_json, load_yaml, save_json

UA = "FishVideoSkill/2.0 (+https://imutechz.com)"
TIMEOUT = 20


class NetError(FishError):
    """A network call failed (soft: callers warn and carry on)."""


def _redact(url: str) -> str:
    """Strip key/token query params so errors never leak a secret."""
    try:
        p = urllib.parse.urlsplit(url)
        q = [(k, "***" if k.lower() in ("key", "token", "api_key", "client_id") else v) for k, v in urllib.parse.parse_qsl(p.query)]
        return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), ""))
    except Exception:
        return url.split("?")[0]


def http_only(url: str) -> str:
    """Refuse anything that is not http(s): a download URL often comes from a third-party API response,
    and urllib would otherwise open file:// and ftp:// too."""
    if urllib.parse.urlsplit(str(url)).scheme.lower() not in ("http", "https"):
        raise NetError(f"refused a URL that is not http(s): {str(url)[:60]}")
    return str(url)


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Every redirect target must still be http(s), and a credential never follows a redirect to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        http_only(urllib.parse.urljoin(req.full_url, newurl))
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(new.full_url).netloc.lower() != urllib.parse.urlsplit(req.full_url).netloc.lower():
            for h in ("Authorization", "Cookie", "Proxy-authorization"):
                new.remove_header(h)
        return new


urllib.request.install_opener(urllib.request.build_opener(_SafeRedirect()))


def private_host(host: str | None) -> bool:
    """True for a host that must not be fetched on a user's behalf: localhost, .local / .internal names, and any
    loopback, private, link-local, reserved or unspecified address (a name is resolved and every answer is checked)."""
    import ipaddress
    import socket
    h = (host or "").strip("[]").lower().rstrip(".")
    if not h or h == "localhost" or h.endswith((".localhost", ".local", ".internal", ".localdomain", ".home.arpa")):
        return True
    try:
        addrs = [ipaddress.ip_address(h)]
    except ValueError:
        try:
            addrs = [ipaddress.ip_address(a[4][0].split("%")[0]) for a in socket.getaddrinfo(h, None)]
        except (OSError, ValueError):
            return False                          # unresolvable: the browser will fail on its own
    return any(a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_unspecified or a.is_multicast for a in addrs)


def strip_userinfo(url: str) -> str:
    """The URL without user:pass@ (so a credential is never logged, written to credits.json or sent to a browser)."""
    sp = urllib.parse.urlsplit(url)
    host = (sp.hostname or "")
    if ":" in host:
        host = f"[{host}]"
    return urllib.parse.urlunsplit((sp.scheme, host + (f":{sp.port}" if sp.port else ""), sp.path, sp.query, ""))


def safe_name(text: str, maxlen: int = 80) -> str:
    """A file-name-safe token: ids and titles from an API never choose a folder (no slashes, no leading dots)."""
    import re
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", str(text)).strip("-.")
    s = re.sub(r"\.{2,}", ".", s)
    return s[:maxlen] or "x"


def build_url(url: str, params: dict | None = None) -> str:
    if not params:
        return url
    clean = {k: v for k, v in params.items() if v is not None}
    return url + ("&" if "?" in url else "?") + urllib.parse.urlencode(clean, doseq=True)


def fetch(url: str, params: dict | None = None, headers: dict | None = None, timeout: float = TIMEOUT, retries: int = 1) -> bytes:
    full = http_only(build_url(url, params))
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(full, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            break
        except Exception as e:  # URLError, timeout, ssl...
            last = e
            break
    why = f"HTTP {last.code}" if isinstance(last, urllib.error.HTTPError) else str(getattr(last, "reason", last))
    raise NetError(f"request failed ({why}): {_redact(full)}")


def fetch_json(url: str, params: dict | None = None, headers: dict | None = None, timeout: float = TIMEOUT) -> Any:
    raw = fetch(url, params, headers, timeout)
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        raise NetError(f"not JSON from {_redact(build_url(url, params))}")


def download_file(url: str, dest: Path | str, headers: dict | None = None, timeout: float = 60,
                  max_bytes: int | None = None, types: tuple[str, ...] | None = None) -> Path:
    """Stream url to dest (atomic via .part).

    max_bytes stops a download that grows past the cap; types is a tuple of allowed Content-Type
    prefixes ("image/", "audio/"), checked when the server sends one.
    """
    http_only(url)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    h = {"User-Agent": UA}
    h.update(headers or {})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r, tmp.open("wb") as fh:
            ctype = str(getattr(r, "headers", None) and r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if types and ctype and not ctype.startswith(tuple(types)):
                raise NetError(f"unexpected content type '{ctype}' (wanted {', '.join(types)})")
            total = 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                total += len(chunk)
                if max_bytes and total > max_bytes:
                    raise NetError(f"larger than the {max_bytes // (1 << 20)} MB cap")
                fh.write(chunk)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise NetError(f"download failed ({getattr(e, 'reason', e)}): {_redact(url)}")
    tmp.replace(dest)
    return dest


# ------------------------------------------------------------------ licences
def norm_license(raw: str | None, url: str | None = None) -> dict:
    """Normalise a licence string/url -> {label, url, ok, attribution}.

    ok=False for NC / ND / unknown restrictive licences (we drop those).
    """
    s = f"{raw or ''} {url or ''}".lower()
    if not s.strip():
        return {"label": "unknown", "url": "", "ok": False, "attribution": True}
    if "-nc" in s or " nc" in s or "noncommercial" in s or "non-commercial" in s or "-nd" in s or "noderiv" in s or "no deriv" in s or "sampling" in s:
        return {"label": str(raw or url), "url": url or "", "ok": False, "attribution": True}
    if "publicdomain/zero" in s or "cc0" in s or "creative commons 0" in s or "cc zero" in s or "zero" in s.split():
        return {"label": "CC0", "url": "https://creativecommons.org/publicdomain/zero/1.0/", "ok": True, "attribution": False}
    if "pdm" in s or "public domain" in s or "publicdomain/mark" in s or "licenses/publicdomain" in s or s.strip().startswith("pd"):
        return {"label": "Public Domain", "url": "https://creativecommons.org/publicdomain/mark/1.0/", "ok": True, "attribution": False}
    import re
    ver = re.search(r"(\d\.\d)", s)
    v = ver.group(1) if ver else "4.0"
    if "by-sa" in s or "by sa" in s or "attribution-sharealike" in s or "attribution share" in s:
        return {"label": f"CC BY-SA {v}", "url": f"https://creativecommons.org/licenses/by-sa/{v}/", "ok": True, "attribution": True}
    if "licenses/by/" in s or "cc by" in s or "cc-by" in s or s.strip().startswith("by ") or s.strip() == "by" or "attribution" in s:
        return {"label": f"CC BY {v}", "url": f"https://creativecommons.org/licenses/by/{v}/", "ok": True, "attribution": True}
    return {"label": str(raw or url), "url": url or "", "ok": False, "attribution": True}


_CC_PATHS = [(r"/licenses/by/(\d\.\d)/?", "CC BY", "licenses/by", True), (r"/licenses/by-sa/(\d\.\d)/?", "CC BY-SA", "licenses/by-sa", True),
             (r"/publicdomain/zero/1\.0/?", "CC0", None, False), (r"/publicdomain/mark/1\.0/?", "Public Domain", None, False)]


def strict_license_url(url: str | None) -> dict:
    """Judge a licence link that came from a provider's response (an uploader can write anything there).
    Only a creativecommons.org URL in a known licence path counts: {ok, label, url, attribution, restricted}.
    A creativecommons.org NC / ND link is `restricted` (dropped); every other link is just not ok (unverified)."""
    import re
    try:
        sp = urllib.parse.urlsplit(str(url or "").strip())
    except ValueError:
        return {"ok": False, "restricted": False}
    if sp.scheme.lower() not in ("http", "https") or (sp.hostname or "").lower() not in ("creativecommons.org", "www.creativecommons.org") or sp.port or sp.username:
        return {"ok": False, "restricted": False}
    for pat, label, base, attr in _CC_PATHS:
        m = re.fullmatch(pat, sp.path)
        if m:
            ver = m.group(1) if m.groups() else ""
            lab = f"{label} {ver}".strip()
            return {"ok": True, "label": lab, "url": f"https://creativecommons.org/{base}/{ver}/" if base else f"https://creativecommons.org{sp.path.rstrip('/')}/",
                    "attribution": attr, "restricted": False}
    return {"ok": False, "restricted": bool(re.search(r"/licenses/by-(nc|nd)", sp.path))}


# ------------------------------------------------------------------ risk tiers
# Every candidate and credit record carries one:
#   safe        licence evidence that allows commercial reuse (public domain, CC0, CC BY / BY-SA, a stock
#               library licence), or a sound / image generated by this code
#   platform    no open licence; shown under the source's own terms (a screenshot of a website, a logo
#               whose file licence is not open)
#   unverified  no licence evidence at all (a meme template, a viral sound, an archive item with no licence)
RISKS = ("safe", "platform", "unverified")
POLICIES = ("none", "safe", "viral")


def risk_of(rec: dict) -> str:
    """A record's tier. Records written before 2.3 have no field: every provider then kept vetted licences only."""
    r = rec.get("risk")
    return r if r in RISKS else "safe"


def memes_policy(project: Path | str | None) -> str:
    """brief.yaml -> memes.policy: none | safe (the default) | viral."""
    f = Path(project) / "brief.yaml" if project else None
    if not f or not f.exists():
        return "safe"
    pol = ((load_yaml(f) or {}).get("memes") or {}).get("policy")
    return pol if pol in POLICIES else "safe"


def check_risk(project: Path | str | None, rec: dict, accept_risk: bool = False) -> None:
    """Refuse an unverified asset unless the project opted in (memes.policy: viral) or the caller passed --accept-risk."""
    if risk_of(rec) != "unverified" or accept_risk or memes_policy(project) == "viral":
        return
    raise FishError(f"{rec.get('id') or rec.get('title')}: the licence is not verified, so it was refused. This project is licence-safe. "
                    "To use it anyway, set `memes.policy: viral` in brief.yaml (interview question `memes`) or pass --accept-risk. "
                    "It can get the video claimed, muted or taken down.")


# ------------------------------------------------------------------ untrusted SVG
SVG_TAGS = {"svg", "g", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon", "defs", "lineargradient", "radialgradient",
            "stop", "clippath", "mask", "use", "symbol", "title", "desc", "text", "tspan", "pattern"}
SVG_MAX = 512 * 1024


def sanitize_svg(text: str | bytes) -> str:
    """An SVG from the network, reduced to drawing elements: no scripts, event handlers, foreign content,
    animation, styles or external references. The stage loads assets in a browser, so they are untrusted."""
    import re
    import xml.etree.ElementTree as ET
    raw = text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text)
    if len(raw) > SVG_MAX:
        raise FishError("SVG refused: larger than 512 KB")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", raw, re.I):
        raise FishError("SVG refused: it declares a DOCTYPE or entities")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise FishError(f"SVG refused: not well-formed ({e})")
    except RecursionError:
        raise FishError("SVG refused: nested too deeply")
    local = lambda name: name.rsplit("}", 1)[-1]
    if local(root.tag).lower() != "svg":
        raise FishError("SVG refused: the root element is not <svg>")

    def clean(node, depth: int = 0) -> None:
        if depth > 64:
            raise FishError("SVG refused: nested more than 64 levels")
        for child in list(node):
            if local(child.tag).lower() not in SVG_TAGS:
                node.remove(child)
                continue
            clean(child, depth + 1)
            if local(child.tag).lower() == "use" and not any(local(k).lower() == "href" for k in child.attrib):
                node.remove(child)  # its external reference was stripped: nothing left to draw
        for k in list(node.attrib):
            name, val = local(k).lower(), str(node.attrib[k])
            if "\\" in val:
                del node.attrib[k]              # a CSS escape can spell url( past the filter below
            elif name.startswith("on") or name == "style" and re.search(r"url\(|@import|expression", val, re.I):
                del node.attrib[k]
            elif name == "href" and not val.startswith("#"):
                del node.attrib[k]
            elif re.search(r"javascript:|data:text/html", val, re.I) or re.search(r"url\(\s*['\"]?(?!#)", val, re.I):
                del node.attrib[k]

    try:
        clean(root)
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
        return ET.tostring(root, encoding="unicode")
    except RecursionError:
        raise FishError("SVG refused: nested too deeply")


# ------------------------------------------------------------------ credits
def credits_path(project: Path | str) -> Path:
    return Path(project) / "assets" / "credits.json"


def load_credits(project: Path | str) -> list[dict]:
    d = load_json(credits_path(project), default=[])
    return d if isinstance(d, list) else d.get("items", [])


def add_credit(project: Path | str, rec: dict) -> bool:
    """Append rec to assets/credits.json unless (provider, id) is already there. True if added."""
    items = load_credits(project)
    key = (rec.get("provider"), str(rec.get("id")))
    for it in items:
        if (it.get("provider"), str(it.get("id"))) == key:
            if rec.get("file") and it.get("file") != rec["file"]:
                it["file"] = rec["file"]
                save_json(credits_path(project), items)
            return False
    items.append(rec)
    save_json(credits_path(project), items)
    return True


def project_of(path: Path | str) -> Path | None:
    """Walk up from path to the folder holding brief.yaml."""
    p = Path(path).resolve()
    for q in [p] + list(p.parents):
        if (q / "brief.yaml").exists():
            return q
    return None


PROVIDER_NAMES = {"pexels": "Pexels", "pixabay": "Pixabay", "openverse": "Openverse", "wikimedia": "Wikimedia Commons",
                  "nasa": "NASA Image and Video Library", "loc": "Library of Congress", "freesound": "Freesound", "kenney": "Kenney", "youtube": "YouTube",
                  "archive": "Internet Archive", "imgflip": "Imgflip", "simpleicons": "Simple Icons", "iconify": "Iconify",
                  "openmoji": "OpenMoji", "twemoji": "Twemoji", "screenshot": "website screenshot", "synth": "Fish Video Skill (synthesised)",
                  "own": "supplied by the user"}


def credit_line(rec: dict) -> str:
    title = rec.get("title") or "Untitled"
    author = rec.get("author") or "unknown"
    prov = PROVIDER_NAMES.get(rec.get("provider"), rec.get("provider") or "")
    src = rec.get("url") or ""
    lic = rec.get("license") or ""
    if rec.get("attribution_required"):
        lurl = rec.get("license_url") or ""
        return f'"{title}" by {author} ({src}) is licensed under {lic}{f" ({lurl})" if lurl else ""}. Source: {prov}.'.replace(" ()", "")
    return f'{title} by {author} via {prov} ({src}), {lic}.'.replace(" ()", "")


def _uniq(lines) -> list[str]:
    """Drop repeated lines (a clip cut from a downloaded film credits the film twice), keep order."""
    return list(dict.fromkeys(lines))


def credits_text(project: Path | str) -> str:
    """Description-ready credits block built from assets/credits.json. Assets whose licence is not open
    are listed apart, so nobody publishes them by accident."""
    items = load_credits(project)
    safe = [i for i in items if risk_of(i) == "safe"]
    must = _uniq(credit_line(i) for i in safe if i.get("attribution_required"))
    nice = _uniq(credit_line(i) for i in safe if not i.get("attribution_required"))
    out: list[str] = []
    if must:
        out += ["Credits:"] + [f"- {x}" for x in must]
    if nice:
        out += ([""] if out else []) + ["Also thanks to:"] + [f"- {x}" for x in nice]
    for tier, head in (("platform", "Shown under the source's own terms (no open licence):"),
                       ("unverified", "LICENCE NOT VERIFIED (review before publishing; these can be claimed, muted or taken down):")):
        rows = _uniq(credit_line(i) for i in items if risk_of(i) == tier)
        if rows:
            out += ([""] if out else []) + [head] + [f"- {x}" for x in rows]
    return "\n".join(out)


def risky(project: Path | str) -> list[dict]:
    """Credit records that are not `safe`, for QA and the package."""
    return [i for i in load_credits(project) if risk_of(i) != "safe"]


def claim_license(source: str | None, license: str | None) -> tuple[str, str, str, bool]:
    """(risk, licence label, licence url, attribution) for an asset the user brings."""
    if license:
        nl = norm_license(license)
        if nl["ok"]:
            return "safe", nl["label"], nl["url"], nl["attribution"]
        return "unverified", f"{license} (not an open licence)", "", False
    if source == "own":
        return "safe", "Own work, or used with the owner's permission", "", False
    return "unverified", "No licence evidence", "", False
