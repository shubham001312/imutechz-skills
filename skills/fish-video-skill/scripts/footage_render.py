"""fish-video-skill footage pipeline. Footage-led Shorts renderer (1080x1920, 30 fps): real clips + kinetic overlays + optional word captions + mixed audio.

    fishvideo footage render <dir> [--preview]        (--preview = half resolution, fast). Spec: references/footage-shorts.md

Reads <dir>/spec.yaml and <dir>/build/words.json (from footage_voice.py). Writes <dir>/out/video.mp4 and captions.srt.
"""
import json, math, random, subprocess, sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))
from fvcore import ffmpeg_bin  # noqa: E402
FF = ffmpeg_bin()
ENG = SKILL
FPS = 30
W, H = 1080, 1920
SR = 48000
FONTS = {"anton": str(SKILL / "assets/fonts/Anton-Regular.ttf"), "bebas": str(SKILL / "assets/fonts/BebasNeue-Regular.ttf"),
         "mont": str(SKILL / "assets/fonts/Montserrat.ttf")}
YELLOW = (255, 214, 0)


# ------------------------------------------------------------------ easing
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease_out_back(x, s=1.9):
    x = clamp(x) - 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2


def ease_out_expo(x):
    x = clamp(x)
    return 1 if x >= 1 else 1 - 2 ** (-10 * x)


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def hexrgb(h, a=255):
    if isinstance(h, (list, tuple)):
        return tuple(h) + ((a,) if len(h) == 3 else ())
    h = h.lstrip("#")
    if len(h) == 8:
        a = int(h[6:8], 16) * a // 255
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


# ------------------------------------------------------------------ text rendering (cached)
@lru_cache(maxsize=64)
def font(name, size, weight=None):
    f = ImageFont.truetype(FONTS[name], size)
    if name == "mont":
        try:
            f.set_variation_by_axes([weight or 800])
        except Exception:
            pass
    return f


@lru_cache(maxsize=512)
def text_img(text, fname="anton", size=200, color="#FFFFFF", stroke=0, stroke_color="#000000", box=None, pad=(34, 14),
             glow=0, glow_color=None, weight=None, shadow=True, radius=18):
    """RGBA image of a single line of text, with optional box (chip), stroke, glow and drop shadow."""
    f = font(fname, size, weight)
    l, t, r, b = f.getbbox(text, stroke_width=stroke)
    tw, th = r - l, b - t
    px, py = pad if box else (0, 0)
    m = max(glow * 3, 24)
    Wd, Hd = tw + 2 * px + 2 * m, th + 2 * py + 2 * m
    im = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0 = m + px - l, m + py - t
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        if box:
            sd.rounded_rectangle([m, m + 10, m + tw + 2 * px, m + th + 2 * py + 10], radius=radius, fill=(0, 0, 0, 150))
        else:
            sd.text((x0, y0 + 8), text, font=f, fill=(0, 0, 0, 170), stroke_width=stroke, stroke_fill=(0, 0, 0, 170))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(10)))
        d = ImageDraw.Draw(im)
    if glow:
        g = Image.new("RGBA", im.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        gc = hexrgb(glow_color or color, 255)
        if box:
            gd.rounded_rectangle([m, m, m + tw + 2 * px, m + th + 2 * py], radius=radius, fill=gc)
        else:
            gd.text((x0, y0), text, font=f, fill=gc, stroke_width=stroke + 4, stroke_fill=gc)
        g = g.filter(ImageFilter.GaussianBlur(glow))
        im = Image.alpha_composite(im, g)
        d = ImageDraw.Draw(im)
    if box:
        d.rounded_rectangle([m, m, m + tw + 2 * px, m + th + 2 * py], radius=radius, fill=hexrgb(box))
    d.text((x0, y0), text, font=f, fill=hexrgb(color), stroke_width=stroke, stroke_fill=hexrgb(stroke_color))
    return im


def paste(canvas, im, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    """alpha-composite RGBA `im` centred at (cx, cy) with scale / opacity / rotation."""
    if alpha <= 0.01 or scale <= 0.01:
        return
    if abs(scale - 1) > 0.005:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
    if abs(rot) > 0.05:
        im = im.rotate(rot, Image.BILINEAR, expand=True)
    if alpha < 0.999:
        a = im.getchannel("A").point(lambda v: int(v * alpha))
        im = im.copy(); im.putalpha(a)
    x, y = int(cx - im.width / 2), int(cy - im.height / 2)
    canvas.alpha_composite(im, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))


# ------------------------------------------------------------------ time anchors
class Clock:
    def __init__(self, words, end):
        self.a = words["anchors"]; self.end = end

    def t(self, v, default=None):
        if v is None:
            return default
        if isinstance(v, (int, float)):
            return float(v)
        v = str(v)
        for op in ("+", "-"):
            if op in v[1:]:
                k, d = v.rsplit(op, 1)
                return self.t(k) + (float(d) if op == "+" else -float(d))
        if v == "end":
            return self.end
        if v not in self.a:
            raise SystemExit(f"unknown anchor {v!r}; have {list(self.a)}")
        return float(self.a[v])


# ------------------------------------------------------------------ footage
def probe(src):
    out = subprocess.run([FF, "-i", str(src)], capture_output=True, text=True).stderr
    import re
    m = re.search(r"Stream.*Video:.* (\d{2,5})x(\d{2,5})", out)
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    dur = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3)) if d else 0
    return int(m.group(1)), int(m.group(2)), dur


class Shot:
    """Streams frames of one shot (cover-cropped to the frame aspect, with headroom for zoom)."""

    def __init__(self, vdir, spec, t0, t1, scale):
        self.s, self.t0, self.t1 = spec, t0, t1
        self.vdir = vdir
        self.src = str((vdir / spec["src"]).resolve()) if not str(spec["src"]).startswith("/") else spec["src"]
        self.w, self.h = int(W * scale), int(H * scale)
        self.is_img = self.src.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".tif"))
        self.n = int(round((t1 - t0) * FPS)) + 2
        self.k = 0
        self.last = None
        self.proc = None
        # cover size with headroom: decode at cover * 1.0 of (w, h)
        if self.is_img:
            im = Image.open(self.src).convert("RGB")
            self.img = im
        else:
            sw, sh, sdur = probe(self.src)
            rate = float(spec.get("rate", 1.0))
            cw, ch = self.w, self.h
            if sw / sh > cw / ch:          # wider: fit height
                dh = int(ch * spec.get("pre", 1.0)); dw = int(round(sw * dh / sh / 2) * 2)
            else:
                dw = int(cw * spec.get("pre", 1.0)); dh = int(round(sh * dw / sw / 2) * 2)
            self.dw, self.dh = dw, dh
            vf = f"setpts=PTS/{rate},fps={FPS},scale={dw}:{dh}:flags=lanczos"
            if spec.get("reverse"):
                vf = "reverse," + vf
            args = [FF, "-loglevel", "error", "-ss", str(spec.get("in", 0)), "-t", str((t1 - t0) * rate + 1.0), "-i", self.src,
                    "-an", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
            self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10 ** 8)

    def frame(self, t):
        """frame for absolute time t, already zoomed/cropped to (w, h) as PIL RGB"""
        s = self.s
        if self.is_img:
            base = self.img
        else:
            raw = self.proc.stdout.read(self.dw * self.dh * 3) if self.proc else b""
            if len(raw) == self.dw * self.dh * 3:
                self.last = Image.frombuffer("RGB", (self.dw, self.dh), raw, "raw", "RGB", 0, 1)
            base = self.last if self.last is not None else Image.new("RGB", (self.dw, self.dh))
        u = clamp((t - self.t0) / max(0.01, self.t1 - self.t0))
        e = ease_io(u) if s.get("ease", True) else u
        if s.get("card"):
            return self.card_frame(base, t, e)
        z = s.get("z0", 1.04) + (s.get("z1", 1.14) - s.get("z0", 1.04)) * e
        fx = s.get("fx", 0.5) + (s.get("fx1", s.get("fx", 0.5)) - s.get("fx", 0.5)) * e
        fy = s.get("fy", 0.5) + (s.get("fy1", s.get("fy", 0.5)) - s.get("fy", 0.5)) * e
        bw, bh = base.size
        # region of the base image that maps to the output, cover-fit then zoom
        cover = max(self.w / bw, self.h / bh) * z
        rw, rh = self.w / cover, self.h / cover
        cx = fx * bw; cy = fy * bh
        x0 = min(max(0, cx - rw / 2), bw - rw); y0 = min(max(0, cy - rh / 2), bh - rh)
        if s.get("shake"):
            amp = s["shake"] * 6
            x0 += math.sin(t * 13.1) * amp + math.sin(t * 7.3) * amp * 0.6
            y0 += math.cos(t * 11.7) * amp * 0.8
            x0 = min(max(0, x0), bw - rw); y0 = min(max(0, y0), bh - rh)
        return base.transform((self.w, self.h), Image.EXTENT, (x0, y0, x0 + rw, y0 + rh), Image.BILINEAR)

    def card_frame(self, base, t, e):
        """a region of the source shown as a floating rounded card over a background"""
        s = self.s; bw, bh = base.size
        x0, y0, x1, y1 = s["card"]
        reg = base.crop((int(x0 * bw), int(y0 * bh), int(x1 * bw), int(y1 * bh)))
        z = s.get("z0", 1.0) + (s.get("z1", 1.06) - s.get("z0", 1.0)) * e
        cw = int(s.get("card_w", 1000) / 1080 * self.w * z)
        ch = int(reg.height * cw / reg.width)
        reg = reg.resize((cw, ch), Image.LANCZOS)
        bg = s.get("bg", "blur")
        if bg == "blur":
            small = base.resize((max(1, self.w // 10), max(1, int(self.w // 10 * bh / bw))), Image.BILINEAR)
            cover = max(self.w / small.width, self.h / small.height)
            sm = small.resize((int(small.width * cover) + 2, int(small.height * cover) + 2), Image.BILINEAR)
            sm = sm.crop(((sm.width - self.w) // 2, (sm.height - self.h) // 2, (sm.width - self.w) // 2 + self.w, (sm.height - self.h) // 2 + self.h))
            canvas = sm.filter(ImageFilter.GaussianBlur(6)).point(lambda v: int(v * 0.55))
        else:
            canvas = Image.new("RGB", (self.w, self.h), bg)
            if s.get("bg_img"):
                bi = load_png(str(s["bg_img"]), self.w).convert("RGB")
                canvas.paste(bi, (0, 0))
        if s.get("bg_seq"):
            fs = seq_files(str((self.vdir / s["bg_seq"]).resolve()))
            fr = load_png(fs[int(t * FPS) % len(fs)], int(self.w * s.get("bg_seq_w", 1.5)))
            fr = fr.rotate(t * s.get("bg_spin", 12), Image.BILINEAR)
            a = fr.getchannel("A").point(lambda v: int(v * s.get("bg_seq_alpha", 0.13)))
            fr = fr.copy(); fr.putalpha(a)
            canvas = canvas.convert("RGBA")
            canvas.alpha_composite(fr, ((self.w - fr.width) // 2, int(self.h * s.get("bg_seq_y", 0.5) - fr.height / 2)) if fr.width <= self.w else (0, 0),
                                   ((fr.width - self.w) // 2, max(0, int(fr.height / 2 - self.h * s.get("bg_seq_y", 0.5)))) if fr.width > self.w else (0, 0))
            canvas = canvas.convert("RGB")
        r = int(28 * self.w / 1080)
        mask = Image.new("L", (cw, ch), 0); ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=r, fill=255)
        bob = math.sin(t * 2.3) * 10 * self.w / 1080 * s.get("float", 1)
        cx = self.w // 2 - cw // 2 + int(math.sin(t * 1.7) * 6 * self.w / 1080 * s.get("float", 1))
        cy = int(s.get("card_y", 0.5) * self.h - ch / 2 + (s.get("card_dy", 0) * self.h) * (1 - e) + bob)
        sh = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([cx, cy + int(18 * self.w / 1080), cx + cw, cy + ch + int(18 * self.w / 1080)], radius=r, fill=(0, 0, 0, 120))
        canvas = canvas.convert("RGBA"); canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(int(22 * self.w / 1080))))
        canvas = canvas.convert("RGB"); canvas.paste(reg, (cx, cy), mask)
        return canvas

    def close(self):
        if self.proc:
            self.proc.stdout.close(); self.proc.kill()


# ------------------------------------------------------------------ looks
def make_vignette(w, h, strength):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 * 0.8 + ((yy - h / 2) / (h / 2)) ** 2)
    v = 1 - strength * clamp_np((r - 0.55) / 0.9)
    return v[..., None]


def clamp_np(x):
    return np.clip(x, 0, 1)


def grade(arr, look, vign, t, contrast=1.06, sat=1.1):
    a = arr.astype(np.float32)
    if look == "bw":
        g = a.mean(axis=2, keepdims=True); a = np.repeat(g, 3, axis=2); sat = 1
    if look == "vintage":
        a = a * np.array([1.06, 1.0, 0.9], np.float32) + 6
    if look == "cool":
        a = a * np.array([0.94, 1.0, 1.08], np.float32)
    if look == "warm":
        a = a * np.array([1.08, 1.0, 0.92], np.float32)
    if look == "teal":
        lum = a.mean(axis=2, keepdims=True) / 255
        a = a + (1 - lum) * np.array([-10, 4, 14], np.float32) + lum * np.array([12, 4, -10], np.float32)
    if sat != 1:
        g = a.mean(axis=2, keepdims=True); a = g + (a - g) * sat
    a = (a - 128) * contrast + 128
    a = a * vign
    if look in ("vintage", "bw"):
        rng = np.random.default_rng(int(t * 1000))
        a = a + rng.normal(0, 7, a.shape[:2])[..., None].astype(np.float32)
        a = a * (0.97 + 0.03 * math.sin(t * 50))
    return np.clip(a, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ overlays
def ov_alpha(o, t, t0, t1):
    """pop-in / out envelope -> (scale, alpha) or None"""
    if t < t0 or t > t1:
        return None
    din = o.get("in_dur", 0.22); dout = o.get("out_dur", 0.14)
    u = (t - t0) / din
    if o.get("anim", "pop") == "pop":
        sc = 0.35 + 0.65 * ease_out_back(u, 2.2) if u < 1 else 1.0
    elif o["anim"] == "slam":
        sc = 2.2 - 1.2 * ease_out_expo(u) if u < 1 else 1.0
    elif o["anim"] == "rise":
        sc = 1.0
    else:
        sc = 1.0
    al = clamp(u * 2.5)
    if t > t1 - dout:
        v = clamp((t1 - t) / dout); al *= v; sc *= 0.9 + 0.1 * v
    sc *= 1 + o.get("breathe", 0.035) * clamp((t - t0) / max(0.5, t1 - t0))
    return sc, al


def fmt_num(v, o):
    d = o.get("decimals", 0)
    s = f"{v:,.{d}f}" if o.get("commas", True) else f"{v:.{d}f}"
    return o.get("prefix", "") + s + o.get("suffix", "")


@lru_cache(maxsize=4)
def spectrum_img(bw, bh):
    import colorsys
    a = np.zeros((bh, bw, 4), np.uint8)
    for i in range(bw):
        u = i / bw
        if u < 0.72:                       # violet -> red
            r, g, b = colorsys.hsv_to_rgb(0.78 * (1 - u / 0.72), 1, 1); al = 255
        else:                              # infrared: dark magenta fading, hatched
            k = (u - 0.72) / 0.28
            r, g, b = 0.35 * (1 - k) + 0.25, 0.0, 0.3 * (1 - k) + 0.15; al = 235
        a[:, i] = [int(r * 255), int(g * 255), int(b * 255), al]
    im = Image.fromarray(a, "RGBA")
    m = Image.new("L", (bw, bh), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, bw - 1, bh - 1], radius=bh // 2, fill=255)
    im.putalpha(Image.fromarray(np.minimum(np.asarray(m), a[..., 3])))
    return im


@lru_cache(maxsize=32)
def seq_files(d):
    return sorted(str(p) for p in Path(d).glob("f_*.png"))


@lru_cache(maxsize=400)
def load_png(path, width):
    im = Image.open(path).convert("RGBA")
    h = int(im.height * width / im.width)
    return im.resize((width, h), Image.LANCZOS)


@lru_cache(maxsize=8)
def plate_rect(w, h, color):
    m = 30
    im = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([m, m, m + w, m + h], radius=int(min(w, h) * 0.3), fill=hexrgb(color))
    return im.filter(ImageFilter.GaussianBlur(3))


@lru_cache(maxsize=8)
def plate_img(r, color):
    m = 40
    im = Image.new("RGBA", (2 * r + 2 * m, 2 * r + 2 * m), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([m, m, m + 2 * r, m + 2 * r], fill=hexrgb(color))
    return im.filter(ImageFilter.GaussianBlur(18))


def draw_overlay(canvas, o, t, t0, t1, S, vdir):
    env = ov_alpha(o, t, t0, t1)
    if not env:
        return
    sc, al = env
    typ = o["type"]
    x = o.get("x", 540) * S; y = o.get("y", 760) * S
    if o.get("anim") == "rise":
        u = ease_out_expo((t - t0) / 0.35); y += (1 - u) * 120 * S
    rot = o.get("rot", 0)
    style = dict(fname=o.get("font", "anton"), size=int(o.get("size", 190) * S), color=o.get("color", "#FFFFFF"),
                 stroke=int(o.get("stroke", 0) * S), stroke_color=o.get("stroke_color", "#000000"), box=o.get("box"),
                 pad=(int(36 * S), int(12 * S)), glow=int(o.get("glow", 0) * S), glow_color=o.get("glow_color"),
                 weight=o.get("weight"), shadow=o.get("shadow", True), radius=int(o.get("radius", 18) * S))
    if typ == "stamp":
        lines = o["text"].split("\n")
        lh = o.get("size", 190) * S * o.get("lh", 1.05)
        for i, ln in enumerate(lines):
            st = dict(style)
            if o.get("colors"):
                st["color"] = o["colors"][i % len(o["colors"])]
            if o.get("boxes"):
                st["box"] = o["boxes"][i % len(o["boxes"])]
            delay = i * o.get("stagger", 0.0)
            env2 = ov_alpha(o, t, t0 + delay, t1) if delay else env
            if not env2:
                continue
            paste(canvas, text_img(ln, **st), x, y + (i - (len(lines) - 1) / 2) * lh, env2[0], env2[1], rot)
    elif typ == "counter":
        dur = o.get("dur", (t1 - t0) * 0.75)
        u = ease_out_expo((t - t0) / dur) if o.get("ease", "expo") == "expo" else clamp((t - t0) / dur)
        v = o["from"] + (o["to"] - o["from"]) * u
        txt = o["final"] if (o.get("final") and u >= 0.999) else fmt_num(v, o)
        paste(canvas, text_img(txt, **style), x, y, sc, al, rot)
        if o.get("label"):
            ls = dict(style); ls.update(size=int(o.get("label_size", 64) * S), box=o.get("label_box"), color=o.get("label_color", "#FFFFFF"), glow=0, stroke=0)
            paste(canvas, text_img(o["label"], **ls), x, y + o.get("label_dy", 150) * S, sc, al)
    elif typ == "clock":
        dur = o.get("dur", (t1 - t0) * 0.8)
        u = clamp((t - t0) / dur) ** 1.6
        secs = int(o.get("to", 86400) * u)
        txt = f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"
        paste(canvas, text_img(txt, **style), x, y, sc, al, rot)
        if o.get("label"):
            ls = dict(style); ls.update(size=int(o.get("label_size", 60) * S), box=o.get("label_box"), color=o.get("label_color", "#FFFFFF"), glow=0, stroke=0)
            paste(canvas, text_img(o["label"], **ls), x, y + o.get("label_dy", 140) * S, sc, al)
    elif typ == "image":
        im = load_png(str(vdir / o["src"]) if not o["src"].startswith("/") else o["src"], int(o.get("w", 360) * S))
        if o.get("spin"):
            rot = rot + o["spin"] * (t - t0)
        if o.get("plate"):
            if im.width > im.height * 1.6:
                pl = plate_rect(im.width + int(70 * S), im.height + int(60 * S), o.get("plate_color", "#000000B4"))
            else:
                pl = plate_img(int(max(im.width, im.height) * 0.62), o.get("plate_color", "#000000B4"))
            paste(canvas, pl, x, y, sc, al)
        paste(canvas, im, x, y, sc, al, rot)
    elif typ == "bars":
        # comparison bars: items [{label, value, frac, color}]
        items = o["items"]; bw = o.get("bw", 820) * S; bh = o.get("bh", 96) * S; gap = o.get("gap", 210) * S
        y0 = y - (len(items) - 1) * gap / 2
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        for i, it in enumerate(items):
            yy = y0 + i * gap
            u = ease_out_expo((t - t0 - 0.15 - i * o.get("stagger", 0.35)) / 0.9)
            xl = x - bw / 2
            d.rounded_rectangle([xl, yy, xl + bw, yy + bh], radius=int(bh / 2), fill=(255, 255, 255, 46))
            fw = max(bh, bw * it["frac"] * u)
            if u > 0:
                d.rounded_rectangle([xl, yy, xl + fw, yy + bh], radius=int(bh / 2), fill=hexrgb(it.get("color", "#FFD600")))
            lab = text_img(it["label"], "mont", int(50 * S), "#FFFFFF", weight=800, shadow=True)
            layer.alpha_composite(lab, (int(xl - 24 * S), int(yy - lab.height + 30 * S)))
            if u > 0.2:
                val = text_img(it["value"], "anton", int(70 * S), it.get("vcolor", "#000000"), shadow=False)
                vx = int(min(xl + fw - val.width + 12 * S, xl + bw - val.width)) if it["frac"] > 0.3 else int(xl + fw + 4 * S)
                vc = val if it["frac"] > 0.3 else text_img(it["value"], "anton", int(70 * S), "#FFFFFF", shadow=True)
                layer.alpha_composite(vc, (max(0, vx - (0 if it["frac"] > 0.3 else 30)), int(yy + bh / 2 - vc.height / 2)))
        if al < 0.999:
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * al)))
        canvas.alpha_composite(layer)
    elif typ == "beam":
        # glowing pulses travelling from p0 to p1
        (x0, y0), (x1, y1) = [(p[0] * S, p[1] * S) for p in o["path"]]
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        d.line([x0, y0, x1, y1], fill=hexrgb(o.get("color", "#FFD600"), int(90 * al)), width=int(6 * S))
        per = o.get("period", 0.9)
        for k in range(3):
            u = ((t - t0) / per + k / 3) % 1
            px, py = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
            r = 20 * S
            d.ellipse([px - r, py - r, px + r, py + r], fill=hexrgb(o.get("color", "#FFD600"), int(255 * al)))
        glow = layer.filter(ImageFilter.GaussianBlur(14 * S))
        canvas.alpha_composite(glow); canvas.alpha_composite(layer)
    elif typ == "ring":
        # expanding radar rings (signal)
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        for k in range(3):
            u = ((t - t0) / o.get("period", 1.2) + k / 3) % 1
            r = (40 + u * o.get("r", 420)) * S
            d.ellipse([x - r, y - r, x + r, y + r], outline=hexrgb(o.get("color", "#FFD600"), int(255 * (1 - u) * al)), width=int(8 * S))
        canvas.alpha_composite(layer)
    elif typ == "tag":
        # small source / info chip, slides in from the left
        u = ease_out_expo((t - t0) / 0.4)
        im = text_img(o["text"], "mont", int(o.get("size", 38) * S), o.get("color", "#FFFFFF"), box=o.get("box", "#000000B0"),
                      pad=(int(22 * S), int(10 * S)), weight=700, shadow=False, radius=int(12 * S))
        paste(canvas, im, x + (1 - u) * -400 * S, y, 1.0, al)
    elif typ == "imgseq":
        d = Path(str(vdir / o["dir"]) if not o["dir"].startswith("/") else o["dir"])
        fs = seq_files(str(d))
        k = int((t - t0) * FPS * o.get("speed", 1.0)) % len(fs)
        im = load_png(fs[k], int(o.get("w", 600) * S))
        paste(canvas, im, x, y, sc, al, rot)
    elif typ == "spectrum":
        # visible rainbow bar + an infrared zone past red, a marker slides into the IR zone
        bw = int(o.get("bw", 900) * S); bh = int(o.get("bh", 70) * S)
        im = spectrum_img(bw, bh)
        u = ease_out_expo((t - t0) / 0.5)
        x0 = int(x - bw / 2); y0 = int(y - bh / 2)
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        layer.alpha_composite(im.crop((0, 0, max(1, int(bw * u)), bh)), (x0, y0))
        d = ImageDraw.Draw(layer)
        f = text_img("VISIBLE LIGHT", "mont", int(38 * S), "#FFFFFF", weight=800)
        layer.alpha_composite(f, (int(x0 + bw * 0.36 - f.width / 2), int(y0 - f.height + 16 * S)))
        g = text_img("INFRARED", "mont", int(38 * S), "#FF4FD8", weight=900)
        layer.alpha_composite(g, (int(x0 + bw * 0.86 - g.width / 2), int(y0 + bh - 10 * S)))
        mv = clamp((t - t0 - 0.5) / 0.8)
        mx = x0 + bw * (0.3 + 0.56 * ease_io(mv)); my = y0 - 6 * S
        d.polygon([(mx - 22 * S, my - 34 * S), (mx + 22 * S, my - 34 * S), (mx, my)], fill=(255, 255, 255, 255))
        if al < 0.999:
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * al)))
        canvas.alpha_composite(layer)
    elif typ == "arrow":
        # animated chevrons pointing up or down, scrolling in that direction
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        dirn = -1 if o.get("dir", "down") == "up" else 1
        col = o.get("color", "#FF3B30"); n = o.get("n", 3); sz = o.get("size", 110) * S; gapv = sz * 0.75
        for k in range(n):
            ph = ((t - t0) * o.get("speed", 1.6) + k / n) % 1
            yy = y + dirn * (ph - 0.5) * gapv * n
            a = int(255 * al * math.sin(math.pi * ph))
            tip = yy + dirn * sz * 0.45
            d.line([(x - sz, yy - dirn * sz * 0.35), (x, tip), (x + sz, yy - dirn * sz * 0.35)], fill=hexrgb(col, a), width=int(sz * 0.28), joint="curve")
        g = layer.filter(ImageFilter.GaussianBlur(10 * S))
        canvas.alpha_composite(g); canvas.alpha_composite(layer)
    elif typ == "card":
        # document card: white rounded panel with lines [{text, size, color, font, weight}]
        cw = int(o.get("w", 860) * S); padc = int(46 * S)
        imgs = [text_img(l["text"], l.get("font", "mont"), int(l.get("size", 44) * S), l.get("color", "#111111"), weight=l.get("weight", 700), shadow=False) for l in o["lines"]]
        chh = sum(i.height - 2 * 24 for i in imgs) + padc * 2 + int(14 * S) * (len(imgs) - 1)
        card = Image.new("RGBA", (cw + 80, chh + 80), (0, 0, 0, 0))
        sh = Image.new("RGBA", card.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle([40, 52, 40 + cw, 52 + chh], radius=int(26 * S), fill=(0, 0, 0, 160))
        card.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
        cd = ImageDraw.Draw(card); cd.rounded_rectangle([40, 40, 40 + cw, 40 + chh], radius=int(26 * S), fill=hexrgb(o.get("bg", "#FFFFFF")))
        if o.get("accent"):
            cd.rounded_rectangle([40, 40, 40 + int(16 * S), 40 + chh], radius=int(8 * S), fill=hexrgb(o["accent"]))
        yy = 40 + padc - 24
        for im in imgs:
            card.alpha_composite(im, (40 + padc - 24, int(yy))); yy += im.height - 48 + int(14 * S)
        u = ease_out_expo((t - t0) / 0.45)
        paste(canvas, card, x, y + (1 - u) * 260 * S, 1.0, al, rot)
    elif typ == "split":
        # two labelled values side by side with VS (e.g. 69 KB vs 3 MB)
        for i, side in enumerate(o["sides"]):
            cx = (x - o.get("dx", 250) * S) if i == 0 else (x + o.get("dx", 250) * S)
            dl = i * o.get("stagger", 0.45)
            e2 = ov_alpha(o, t, t0 + dl, t1)
            if not e2:
                continue
            v = text_img(side["value"], "anton", int(side.get("size", 150) * S), side.get("color", "#FFFFFF"), stroke=int(6 * S), glow=int(side.get("glow", 0) * S), glow_color=side.get("color"))
            paste(canvas, v, cx, y, e2[0], e2[1])
            lb = text_img(side["label"], "mont", int(42 * S), "#FFFFFF", box=side.get("box", "#000000C0"), pad=(int(18 * S), int(8 * S)), weight=800, shadow=False, radius=int(10 * S))
            paste(canvas, lb, cx, y + 130 * S, e2[0], e2[1])
        if o.get("vs", True):
            paste(canvas, text_img("VS", "anton", int(90 * S), "#FFD600", stroke=int(5 * S)), x, y, sc, al)


# ------------------------------------------------------------------ captions
def caption_lines(caps, max_chars=16, max_units=3):
    lines, cur = [], []
    for c in caps:
        cand = cur + [c]
        txt = " ".join(x["text"] for x in cand)
        brk = cur and (len(txt) > max_chars or len(cand) > max_units or c["s"] - cur[-1]["e"] > 0.35)
        if brk:
            lines.append(cur); cur = [c]
        else:
            cur = cand
        if c["text"].rstrip()[-1:] in ".?!,:" and cur:
            lines.append(cur); cur = []
    if cur:
        lines.append(cur)
    return lines


def draw_captions(canvas, lines, t, S, cfg):
    y = cfg.get("y", 1340) * S
    size = int(cfg.get("size", 80) * S)
    for li, ln in enumerate(lines):
        s = ln[0]["s"]; e = lines[li + 1][0]["s"] if li + 1 < len(lines) else ln[-1]["e"] + 0.5
        e = min(e, ln[-1]["e"] + 0.6)
        if not (s - 0.03 <= t < e):
            continue
        u = (t - s) / 0.12
        sc = 0.82 + 0.18 * ease_out_back(u, 2.5) if u < 1 else 1.0
        words = [w["text"].upper().strip(",.") if cfg.get("upper", True) else w["text"] for w in ln]
        imgs = []
        for w, word in zip(ln, words):
            active = w["s"] - 0.04 <= t < (w["e"] + 0.1)
            col = cfg.get("hl", "#FFD600") if active else "#FFFFFF"
            imgs.append(text_img(word, "mont", size, col, stroke=int(11 * S), weight=900, shadow=True))
        space = int(20 * S)
        total = sum(i.width for i in imgs) - (len(imgs) - 1) * int(48 * S) + space * (len(imgs) - 1)
        x = W * S / 2 - total * sc / 2
        for i, im in enumerate(imgs):
            wsc = sc * (1.08 if (ln[i]["s"] - 0.04 <= t < ln[i]["e"] + 0.1) else 1.0)
            paste(canvas, im, x + im.width * sc / 2, y, wsc, 1.0)
            x += (im.width - int(48 * S) + space) * sc
        return


def srt(caps, path):
    def ts(v):
        ms = int(round(v * 1000)); return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"
    lines = caption_lines(caps, 30, 7)
    out = []
    for i, ln in enumerate(lines):
        out.append(f"{i + 1}\n{ts(ln[0]['s'])} --> {ts(ln[-1]['e'] + 0.2)}\n{' '.join(c['text'] for c in ln)}\n")
    Path(path).write_text("\n".join(out))


# ------------------------------------------------------------------ audio
def resolve(vdir, p):
    """A spec path: absolute; else relative to the project; else to the skill; synth SFX (sfx/s-*.wav) come from sfx/synth/,
    made on first use by footage_tools.synth_sfx."""
    p = Path(str(p))
    if p.is_absolute():
        return p
    for c in (Path(vdir) / p, SKILL / p, SKILL / "sfx/synth" / p.name):
        if c.exists():
            return c
    if p.name.startswith("s-") and p.suffix == ".wav":
        import footage_tools
        footage_tools.synth_sfx()
        return SKILL / "sfx/synth" / p.name
    return Path(vdir) / p


def load_audio(path, start=0.0, dur=None):
    args = [FF, "-loglevel", "error", "-ss", str(start)] + (["-t", str(dur)] if dur else []) + ["-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"]
    raw = subprocess.run(args, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def db(x):
    return 10 ** (x / 20)


def mix_audio(vdir, spec, clock, total, out_wav):
    n = int(total * SR) + SR
    mix = np.zeros((n, 2), np.float32)
    voice = load_audio(vdir / "build/voice.wav")
    vo = int(spec.get("voice_offset", 0) * SR)
    mix[vo:vo + len(voice)] += voice[: n - vo] * db(spec.get("voice_gain", 0))
    # voice envelope for ducking
    env = np.abs(voice[:, 0]); k = int(0.15 * SR)
    env = np.convolve(env, np.ones(k) / k, mode="same")
    duck = np.ones(n, np.float32)
    act = np.zeros(n, np.float32); act[vo:vo + len(env)] = np.clip(env / (env.max() * 0.15 + 1e-6), 0, 1)
    m = spec.get("music")
    if m:
        mus = load_audio(resolve(vdir, m["file"]), m.get("start", 0), total + 1)
        L = min(n, len(mus))
        g = db(m.get("gain", -16))
        duck = 1 - (1 - db(m.get("duck", -7))) * act
        mus = mus[:L] * g * duck[:L, None]
        fi = int(m.get("fade_in", 0.05) * SR); mus[:fi] *= np.linspace(0, 1, fi)[:, None]
        mix[:L] += mus
    for s in spec.get("sfx", []):
        f = resolve(vdir, s["file"])
        if not f.exists():
            print("  (missing sfx, skipped)", s["file"]); continue
        a = load_audio(f, s.get("start", 0), s.get("dur"))
        a = a * db(s.get("gain", -6))
        if s.get("dur"):
            fo = int(min(0.15, s["dur"] / 3) * SR); a[-fo:] *= np.linspace(1, 0, fo)[:, None]
        t = clock.t(s["at"]) + s.get("dt", 0)
        i0 = int(max(0, t) * SR); i1 = min(n, i0 + len(a))
        mix[i0:i1] += a[: i1 - i0]
    mix = mix[: int(total * SR)]
    fo = int(0.12 * SR); mix[-fo:] *= np.linspace(1, 0, fo)[:, None]
    tmp = out_wav.with_suffix(".raw.wav")
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    import wave
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(tmp), "-af", "loudnorm=I=-14:TP=-1.0:LRA=9", "-ar", str(SR), str(out_wav)], check=True)


# ------------------------------------------------------------------ main render
def render(vdir: Path, preview=False):
    spec = yaml.safe_load((vdir / "spec.yaml").read_text())
    words = json.loads((vdir / "build/words.json").read_text())
    total = round(words["duration"] + spec.get("tail", 0.45), 3)
    if spec.get("max_len"):
        total = min(total, spec["max_len"])
    clock = Clock(words, total)
    S = 0.5 if preview else 1.0
    w, h = int(W * S), int(H * S)
    out = vdir / "out"; out.mkdir(exist_ok=True)
    shots = spec["shots"]
    starts = [clock.t(s["at"]) for s in shots] + [total]
    starts[0] = 0.0
    vign = make_vignette(w, h, spec.get("vignette", 0.45))
    caps = words["captions"]
    lines = caption_lines(caps, spec.get("cap_chars", 16), spec.get("cap_units", 3))
    ovs = []
    for o in spec.get("overlays", []):
        ovs.append((o, clock.t(o["at"]) + o.get("dt", 0), clock.t(o.get("until"), None) if o.get("until") is not None else None))
    ovs = [(o, a, (b if b is not None else a + o.get("hold", 1.6))) for o, a, b in ovs]
    wav = vdir / "build/mix.wav"
    mix_audio(vdir, spec, clock, total, wav)
    target = out / ("preview.mp4" if preview else "video.mp4")
    enc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
                            "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast" if preview else "slow", "-crf", "23" if preview else "17",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(target)], stdin=subprocess.PIPE)
    nframes = int(round(total * FPS))
    cur, cur_i, prev_frame = None, -1, None
    nxt = None
    for fi in range(nframes):
        t = fi / FPS
        i = max(k for k in range(len(shots)) if starts[k] <= t + 1e-6)
        if i != cur_i:
            if cur:
                cur.close()
            cur = nxt if (nxt and nxt.idx == i) else Shot(vdir, shots[i], starts[i], starts[i + 1], S)
            cur.idx = i; cur_i = i; nxt = None
        sh = shots[cur_i]
        img = cur.frame(t)
        # transition into this shot
        tr = sh.get("trans", "cut"); dt = t - starts[cur_i]
        arr = grade(np.asarray(img), sh.get("look", spec.get("look", "none")), vign, t, spec.get("contrast", 1.06), sh.get("sat", spec.get("sat", 1.1)))
        if cur_i > 0 or tr in ("dip",):
            if tr == "whip" and dt < 0.16:
                k = 1 - dt / 0.16; sh_px = int(k * 260 * S)
                acc = np.zeros_like(arr, np.float32)
                for j in range(6):
                    acc += np.roll(arr, -sh_px + j * sh_px // 6, axis=1)
                arr = (acc / 6).astype(np.uint8)
            elif tr == "flash" and dt < 0.25:
                k = 1 - dt / 0.25; arr = np.clip(arr.astype(np.float32) + 255 * k * 0.85, 0, 255).astype(np.uint8)
            elif tr == "glitch" and dt < 0.14:
                o2 = int(24 * S * (1 - dt / 0.14)); a2 = arr.copy()
                a2[..., 0] = np.roll(arr[..., 0], o2, axis=1); a2[..., 2] = np.roll(arr[..., 2], -o2, axis=1); arr = a2
            elif tr == "dip" and dt < 0.2:
                arr = (arr.astype(np.float32) * (dt / 0.2)).astype(np.uint8)
            elif tr == "zoom" and dt < 0.3:
                k = 1 + 0.22 * (1 - ease_out_expo(dt / 0.3))
                im2 = Image.fromarray(arr); cw, ch = int(w / k), int(h / k)
                arr = np.asarray(im2.crop(((w - cw) // 2, (h - ch) // 2, (w - cw) // 2 + cw, (h - ch) // 2 + ch)).resize((w, h), Image.BILINEAR))
        # whip-out: blur the end of the outgoing shot if the next one whips
        if cur_i + 1 < len(shots) and shots[cur_i + 1].get("trans") == "whip" and starts[cur_i + 1] - t < 0.12:
            k = 1 - (starts[cur_i + 1] - t) / 0.12; sh_px = int(k * 260 * S)
            acc = np.zeros_like(arr, np.float32)
            for j in range(6):
                acc += np.roll(arr, sh_px - j * sh_px // 6, axis=1)
            arr = (acc / 6).astype(np.uint8)
        canvas = Image.fromarray(arr).convert("RGBA")
        # top / bottom darkening for legibility
        for o, a, b in ovs:
            draw_overlay(canvas, o, t, a, b, S, vdir)
        if spec.get("captions", False):      # off by default: YouTube, TikTok and Reels have their own CC; captions.srt is always written
            draw_captions(canvas, lines, t, S, spec.get("caption", {}))
        enc.stdin.write(canvas.convert("RGB").tobytes())
        if fi % 90 == 0:
            print(f"  frame {fi}/{nframes}", flush=True)
    if cur:
        cur.close()
    enc.stdin.close(); enc.wait()
    srt(caps, out / "captions.srt")
    print("wrote", target, f"{total:.2f}s")
    return target


if __name__ == "__main__":
    a = sys.argv[1:]
    render(Path(a[0]), "--preview" in a)
