"""Tools for the footage pipeline: timestamped contact sheets, YouTube search + 1080p download, key-less NASA / Wikimedia
Commons search and download, and synthesised cinematic SFX (sfx/synth/s-*.wav).

    fishvideo footage sheet <video> <out.jpg> [--step 2] [--cols 6] [--start 0] [--end N]
    fishvideo footage yt search "<query>" [-n 6]          id | seconds | title | channel
    fishvideo footage yt get <dir>/assets <id> [<id> ...]  -> assets/yt-<id>.mp4 (<=1080p, H.264 preferred)
    fishvideo footage commons "<query>" [--video] [-n 12]   title | size | licence | url
    fishvideo footage nasa "<query>" [--video] [-n 12]      nasa_id | title | date
    fishvideo footage get <url> <dest>
    fishvideo footage sfx                                  (re)build sfx/synth/
"""
import json, subprocess, sys, tempfile, urllib.parse, urllib.request, wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))
from fvcore import ffmpeg_bin  # noqa: E402

FF = ffmpeg_bin()
FONT = str(SKILL / "assets/fonts/Anton-Regular.ttf")
UA = {"User-Agent": "fish-video-skill/2.8 (footage research)"}
SFX_DIR = SKILL / "sfx/synth"


# ------------------------------------------------------------------ contact sheet
def sheet(src, out, step=3.0, cols=8, start=0.0, end=None, w=320):
    """One frame every `step` seconds with its timestamp: the way to pick in-points and to look at a render."""
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        args = [FF, "-y", "-loglevel", "error", "-ss", str(start)] + (["-to", str(end)] if end else []) + ["-i", str(src),
                "-vf", f"fps=1/{step},scale={w}:-2", f"{td}/f%04d.jpg"]
        subprocess.run(args, check=True)
        fs = sorted(Path(td).glob("f*.jpg"))
        if not fs:
            print("no frames"); return None
        fw, fh = Image.open(fs[0]).size
        rows = (len(fs) + cols - 1) // cols
        S = Image.new("RGB", (cols * fw, rows * fh), "black")
        d = ImageDraw.Draw(S); f = ImageFont.truetype(FONT, 22)
        for i, p in enumerate(fs):
            x, y = (i % cols) * fw, (i // cols) * fh
            S.paste(Image.open(p), (x, y))
            t = start + i * step
            d.rectangle([x, y, x + 70, y + 28], fill="black")
            d.text((x + 4, y + 1), f"{int(t // 60)}:{t % 60:04.1f}", font=f, fill="yellow")
        S.save(out, quality=80)
        print(out, len(fs), "frames")
        return out


# ------------------------------------------------------------------ YouTube
def _ytdlp():
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        return ["yt-dlp"]


def yt_search(q, n=6):
    r = subprocess.run(_ytdlp() + ["--flat-playlist", "--print", "%(id)s | %(duration)s | %(title)s | %(channel)s", f"ytsearch{n}:{q}"],
                       capture_output=True, text=True, timeout=120)
    print(r.stdout.strip())
    return r.stdout


def yt_get(dest, ids):
    """1080p-or-lower mp4 per id into dest/yt-<id>.mp4 (skips files already there)."""
    dest = Path(dest); dest.mkdir(parents=True, exist_ok=True)
    for vid in ids:
        f = dest / f"yt-{vid}.mp4"
        if f.exists():
            continue
        r = subprocess.run(_ytdlp() + ["-q", "--no-warnings", "--ffmpeg-location", FF,
                                      "-f", "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]",
                                      "--merge-output-format", "mp4", "-o", str(dest / f"yt-{vid}.%(ext)s"), f"https://www.youtube.com/watch?v={vid}"],
                           timeout=900)
        print(("ok " if r.returncode == 0 else "FAIL ") + vid)


# ------------------------------------------------------------------ key-less stills and clips
def jget(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.loads(r.read().decode())


def download(url, dest):
    dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r, open(dest, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    print(dest, dest.stat().st_size)
    return dest


def nasa(q, video=False, n=12):
    d = jget("https://images-api.nasa.gov/search", {"q": q, "media_type": "video" if video else "image", "page_size": n})
    for it in d["collection"]["items"][:n]:
        dd = it["data"][0]
        print(f'{dd["nasa_id"]} | {dd.get("title", "")[:80]} | {dd.get("date_created", "")[:10]}')


def commons(q, video=False, n=12):
    d = jget("https://commons.wikimedia.org/w/api.php", {
        "action": "query", "format": "json", "generator": "search", "gsrsearch": q + (" filetype:video" if video else " filetype:bitmap"),
        "gsrnamespace": 6, "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime"})
    for pg in (d.get("query", {}).get("pages", {}) or {}).values():
        ii = pg["imageinfo"][0]; md = ii.get("extmetadata", {})
        lic = (md.get("LicenseShortName") or {}).get("value", "?")
        print(f'{pg["title"][5:][:70]} | {ii.get("width")}x{ii.get("height")} | {lic} | {ii["url"]}')


# ------------------------------------------------------------------ synthesised SFX
SR = 48000
rng = np.random.default_rng(7)


def save(name, x, width=0.25):
    x = x / (np.abs(x).max() + 1e-9) * 0.9
    d = int(0.0007 * SR)                     # cheap stereo: slight delay on the right channel
    r = np.concatenate([np.zeros(d), x[:-d]]) * (1 - width) + x * width
    pcm = (np.stack([x, r], 1) * 32767).astype(np.int16)
    with wave.open(str(SFX_DIR / f"{name}.wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def t_(d):
    return np.arange(int(d * SR)) / SR


def lp(x, a):
    """one-pole low-pass, a in (0,1): higher = brighter; a may be an array"""
    y = np.zeros_like(x); s = 0.0
    a = np.broadcast_to(a, x.shape)
    for i in range(len(x)):
        s += a[i] * (x[i] - s); y[i] = s
    return y


def env(t, att, dec):
    return np.minimum(1, t / max(att, 1e-4)) * np.exp(-np.maximum(0, t - att) / dec)


def whoosh(d=0.9):
    t = t_(d); n = rng.normal(0, 1, len(t))
    sweep = 0.02 + 0.5 * np.sin(np.pi * t / d) ** 3
    x = lp(n, sweep) * np.sin(np.pi * t / d) ** 2
    return x


def boom(d=2.2, f0=58, f1=32):
    t = t_(d); f = f1 + (f0 - f1) * np.exp(-t * 3)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * env(t, 0.005, 0.7) + 0.4 * np.tanh(3 * np.sin(ph)) * env(t, 0.003, 0.25)
    x += lp(rng.normal(0, 1, len(t)), 0.08) * env(t, 0.001, 0.12) * 0.8
    return x


def hit(d=2.5):
    t = t_(d)
    x = boom(d) * 1.0
    x += lp(rng.normal(0, 1, len(t)), 0.35) * env(t, 0.001, 0.06) * 0.9      # transient
    for f, a in ((180, .25), (431, .15), (777, .08)):                         # metallic ring
        x += np.sin(2 * np.pi * f * t) * env(t, 0.002, 0.5) * a
    return x


def riser(d=1.6):
    t = t_(d); f = 200 * (2 ** (t / d * 3))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = (np.sin(ph) * 0.3 + lp(rng.normal(0, 1, len(t)), 0.05 + 0.5 * t / d) * 0.7) * (t / d) ** 2
    return x


def tick():
    t = t_(0.06)
    return np.sin(2 * np.pi * 2400 * t) * env(t, 0.0005, 0.008) + rng.normal(0, 1, len(t)) * env(t, 0.0002, 0.003) * 0.5


def glitch(d=0.35):
    t = t_(d); x = np.zeros(len(t))
    for k in range(7):
        a = int(rng.uniform(0, d * 0.85) * SR); L = int(rng.uniform(0.01, 0.05) * SR)
        f = rng.uniform(300, 3000)
        seg = np.sign(np.sin(2 * np.pi * f * np.arange(L) / SR)) * 0.6 + rng.normal(0, 0.4, L)
        x[a:a + L] += seg[: len(x[a:a + L])]
    return x


def pop():
    t = t_(0.18); f = 900 * np.exp(-t * 25) + 200
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(t, 0.001, 0.05)


def sweep_down(d=1.2):
    t = t_(d); f = 1800 * np.exp(-t * 4) + 60
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(t, 0.01, 0.5) * 0.6 + lp(rng.normal(0, 1, len(t)), 0.1) * env(t, 0.01, 0.3) * 0.4


def heartbeat():
    t = t_(1.0); x = np.zeros(len(t))
    for st, a in ((0.0, 1.0), (0.22, 0.7)):
        tt = t - st; m = tt >= 0
        x[m] += np.sin(2 * np.pi * 50 * tt[m]) * env(tt[m], 0.004, 0.09) * a
    return x


def zap(d=0.7):
    t = t_(d)
    crack = rng.normal(0, 1, len(t)) * env(t, 0.0005, 0.05)
    buzz = np.sign(np.sin(2 * np.pi * 60 * t)) * env(t, 0.002, 0.25) * 0.4
    return crack + buzz + boom(d, 70, 30) * 0.6


def thunder(d=3.0):
    t = t_(d); n = rng.normal(0, 1, len(t))
    rumble = lp(n, 0.02) * env(t, 0.02, 1.0) * 3
    crack = lp(n, 0.5) * env(t, 0.001, 0.08)
    return rumble + crack


SFX = (("s-whoosh", whoosh), ("s-boom", boom), ("s-hit", hit), ("s-riser", riser), ("s-tick", tick), ("s-glitch", glitch),
       ("s-pop", pop), ("s-sweepdown", sweep_down), ("s-heartbeat", heartbeat), ("s-zap", zap), ("s-thunder", thunder))


def synth_sfx(force=False):
    """Write sfx/synth/s-*.wav (deterministic, CC0 by construction: made here, no samples)."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    for name, fn in SFX:
        if force or not (SFX_DIR / f"{name}.wav").exists():
            save(name, fn())
    return sorted(p.name for p in SFX_DIR.glob("s-*.wav"))
