"""Package one footage Short: the house thumbnail (insider cover, through the skill's own thumbnail renderer) and post texts.

    fishvideo footage package <dir>      thumbnail + texts
    fishvideo footage thumb <dir>        thumbnail only

spec.yaml `thumbnail:` (the insider cover: ONE big hero on top, a small lead line, ONE huge keyword, a black chip):
    lead: "free AI that needs"            small line above the keyword
    title: "NO INTERNET"                  the huge keyword, 1-3 words
    mid: "..."                            optional medium line
    chip: "RUNS ON YOUR LAPTOP"           white on black, slightly turned
    hero:                                 the hook: a real picture, never a website screenshot
      video: assets/yt-x.mp4              a frame from footage ...
      t: 26.0
      crop: [0.1, 0, 0.95, 1]             optional, fractions l, t, r, b
      # or: src: assets/photo.png         ... or a picture file
      kind: card                          card (rounded photo) | cutout (transparent PNG over an accent burst)
      cut: true                           cutout from a photo: remove the background with rembg first
      color: true                         keep a cut-out in colour (default: grey, the InsiderForce look)
      ar: 1.0                             card shape (width / height)
    logos: [assets/a.png, assets/b.png]   instead of a hero: a network of 2-7 logo tiles
    logo_fill: 0.6

Writes into <dir>/out/: thumbnail-shorts.png (1080x1920), thumbnail-16x9.png (1280x720), titles.txt, post.txt (title,
description, hashtags), tags.txt, caption.txt (the pinned comment), sources.txt.
"""
import shutil, subprocess, sys
from pathlib import Path

import yaml
from PIL import Image

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))
from fvcore import FishError, ffmpeg_bin  # noqa: E402

FF = ffmpeg_bin()
FV = [sys.executable, str(SKILL / "scripts/fishvideo.py")]


def _frame(src: Path, t: float, out: Path) -> Path:
    subprocess.run([FF, "-y", "-loglevel", "error", "-ss", str(t), "-i", str(src), "-frames:v", "1", str(out)], check=True)
    return out


def _hero_file(vdir: Path, hero: dict, photo: Path) -> str:
    """Materialise the hero picture inside the thumbnail project; returns its project-relative path."""
    photo.mkdir(parents=True, exist_ok=True)
    if hero.get("video"):
        f = _frame(vdir / hero["video"], float(hero.get("t", 1.0)), photo / "hero.png")
    elif hero.get("src"):
        s = vdir / hero["src"]
        if not s.exists():
            raise FishError(f"thumbnail.hero.src {hero['src']!r} not found")
        f = photo / ("hero" + s.suffix.lower()); shutil.copy2(s, f)
    else:
        raise FishError("thumbnail.hero needs `video` (+ t) or `src`")
    if hero.get("crop"):
        im = Image.open(f); W, H = im.size; l, t, r, b = hero["crop"]
        im.crop((int(l * W), int(t * H), int(r * W), int(b * H))).save(f)
    if hero.get("cut"):
        out = photo / "hero-cut.png"
        subprocess.run(FV + ["thumb", "cutout", str(f), "--out", str(out), "--outline", "0", "--glow", "0"], check=True, capture_output=True)
        f = out
    return str(f.relative_to(photo.parent.parent)).replace("\\", "/")


def thumb(vdir: Path) -> list[Path]:
    """Draw the insider cover with the skill's thumbnail step (fishvideo thumbnail) in a small side project, build/thumbproj."""
    spec = yaml.safe_load((vdir / "spec.yaml").read_text())
    th = spec.get("thumbnail")
    if not th:
        raise FishError("spec.yaml has no `thumbnail:` block (lead, title, chip, hero or logos); see footage_package.py")
    P = vdir / "build/thumbproj"
    if not (P / "brief.yaml").exists():
        r = subprocess.run(FV + ["new", str(P), "--recipe", "kinetic-explainer", "--platforms", "shorts,youtube",
                                 "--title", str(th.get("title", spec.get("title", ""))), "--prompt", str(spec.get("title", ""))],
                           capture_output=True, text=True)
        if r.returncode:
            raise FishError("thumbnail project: " + (r.stderr or r.stdout)[-400:])
    photo = P / "assets/photo"
    shutil.rmtree(photo, ignore_errors=True)
    block = {k: th[k] for k in ("lead", "title", "mid", "chip", "handle", "logo_fill") if th.get(k) is not None}
    if th.get("logos"):
        photo.mkdir(parents=True, exist_ok=True)
        items = []
        for i, lg in enumerate(th["logos"]):
            if Path(str(lg)).suffix:                                  # a file: copied in; else a simple-icons slug
                d = photo / f"logo{i}{Path(lg).suffix.lower()}"; shutil.copy2(vdir / lg, d)
                items.append(str(d.relative_to(P)).replace("\\", "/"))
            else:
                items.append(lg)
        block["logos"] = items
        block["allow_unrelated_logos"] = True                         # the brands come from the footage spec, not this side project
    elif th.get("hero"):
        h = th["hero"]
        src = _hero_file(vdir, h, photo)
        kind = h.get("kind") or ("cutout" if src.endswith(".png") and h.get("cut") else "card")
        block["hero"] = {"src": src, "kind": kind, **{k: h[k] for k in ("color", "ar") if k in h}}
    else:
        raise FishError("thumbnail needs a hero (video+t or src) or 2-7 logos")
    sbf = P / "storyboard.yaml"
    sb = yaml.safe_load(sbf.read_text()) or {}
    sb["thumbnail"] = block
    sbf.write_text(yaml.safe_dump(sb, sort_keys=False, allow_unicode=True))
    r = subprocess.run(FV + ["thumbnail", str(P)], capture_output=True, text=True)
    if r.returncode:
        raise FishError("fishvideo thumbnail failed: " + "\n".join(x for x in (r.stdout + r.stderr).splitlines() if "TODO" not in x)[-800:])
    out = vdir / "out"; out.mkdir(exist_ok=True)
    land = next((P / "build/thumbnail/variants").glob("thumb-1-*.png"))
    cover = next((P / "build/thumbnail/covers").glob("cover-shorts-*.png"))
    shutil.copy2(land, out / "thumbnail-16x9.png"); shutil.copy2(cover, out / "thumbnail-shorts.png")
    print(out / "thumbnail-shorts.png"); print(out / "thumbnail-16x9.png")
    return [out / "thumbnail-shorts.png", out / "thumbnail-16x9.png"]


def texts(vdir: Path):
    spec = yaml.safe_load((vdir / "spec.yaml").read_text())
    out = vdir / "out"; out.mkdir(exist_ok=True)
    m = spec.get("meta", {})
    titles = m.get("titles", [spec.get("title", "")])
    (out / "titles.txt").write_text("\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles)) + "\n")
    (out / "tags.txt").write_text(", ".join(m.get("tags", [])) + "\n")
    hashtags = " ".join(m.get("hashtags", []))
    (out / "post.txt").write_text(f"{titles[0]}\n\n{m.get('description', '').strip()}\n\n{hashtags}\n")
    (out / "caption.txt").write_text(m.get("pinned_comment", "").strip() + "\n")
    (out / "sources.txt").write_text("\n".join(m.get("sources", [])) + "\n")
    print("post texts written:", ", ".join(p.name for p in sorted(out.iterdir())))


def run(vdir: Path, thumbnail: bool = True):
    if thumbnail:
        thumb(vdir)
    texts(vdir)


if __name__ == "__main__":
    run(Path(sys.argv[1]))
