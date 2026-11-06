/* Looks: the visual toolkit shared by the collage / studio / neon / footage
   scenes and by main.js (textures, transitions, pop captions).

   - easing: L.bez (cubic-bezier), L.portal (.16,1,.3,1), L.pop3 (0 -> 1.1 -> 1)
   - textures: L.texture(kind, W, H) -> Promise<blob url> (paper is SVG
     feTurbulence + feDiffuseLighting rasterised once, then speckled on a canvas)
   - image treatments: L.treat(url, {bw, halftone, contrast, ...}) -> Promise<blob url>
     (one canvas pass per image, cached); L.setImgFx(img, url, fx) is the
     L.setImg of treated images (the decode is awaited by renderAt)
   - L.cutFilter(): outline + contact shadow as a drop-shadow filter stack
   - shapes: L.chamfer(w, h, c) polygon points, L.icon(name) glyphs
   - drawing: L.handArrow (rough.js curved arrow), L.defs() shared SVG filters
   - backgrounds: L.paperBg, L.studioBg, L.darkBg (grid, dust, vignette)
   - kinetic type: L.slideWords (motion-blur trail), L.subWords (scale + blur fade)
   - camera: L.drift(t, dur) push-in + bob
   - cues: L.cue(lt, type, lvl, extra) where lvl 1 = rich only, 2 = standard,
     3 = minimal (big moments). main.js filters by the sfx density.

   Everything is a pure function of t: seeded rng, no timers, no CSS animation. */
(function () {
  "use strict";
  const L = window.L;
  const { el, clamp, seg, eo, ei } = L;
  const SVGNS = "http://www.w3.org/2000/svg";

  /* ---------------- easing ---------------- */
  L.bez = (x1, y1, x2, y2) => {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const X = (s) => ((ax * s + bx) * s + cx) * s, Y = (s) => ((ay * s + by) * s + cy) * s;
    return (x) => {
      x = clamp(x);
      if (x === 0 || x === 1) return x;
      let lo = 0, hi = 1, s = x;
      for (let i = 0; i < 40; i++) { const v = X(s); if (Math.abs(v - x) < 1e-6) break; if (v < x) lo = s; else hi = s; s = (lo + hi) / 2; }
      return Y(s);
    };
  };
  L.portal = L.bez(0.16, 1, 0.3, 1);
  /* 0 -> 1.1 -> 1 (icon pops) */
  L.pop3 = (p) => { p = clamp(p); return p < 0.6 ? 1.1 * eo(p / 0.6) : 1.1 - 0.1 * L.eio((p - 0.6) / 0.4); };

  /* ---------------- cues ---------------- */
  L.cue = (lt, type, lvl = 2, extra) => Object.assign({ lt: +lt.toFixed(4), type, lvl }, extra || {});
  /* swishes lead the motion they belong to */
  L.SWISH_LEAD = 0.1;

  /* ---------------- shared SVG defs (filters) ---------------- */
  let DEFS = null;
  L.defs = () => {
    if (DEFS) return DEFS;
    const s = document.createElementNS(SVGNS, "svg");
    s.setAttribute("width", 0); s.setAttribute("height", 0);
    s.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
    let h = "";
    /* horizontal motion blur, 8 strengths */
    for (let k = 1; k <= 8; k++) h += `<filter id="fv-mb${k}" x="-50%" y="-20%" width="200%" height="140%"><feGaussianBlur stdDeviation="${k * 3} 0"/></filter>`;
    /* bloom: blurred copies merged under the source */
    h += `<filter id="fv-bloom" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB"><feGaussianBlur in="SourceGraphic" stdDeviation="5" result="b1"/><feGaussianBlur in="SourceGraphic" stdDeviation="14" result="b2"/><feMerge><feMergeNode in="b2"/><feMergeNode in="b2"/><feMergeNode in="b1"/><feMergeNode in="SourceGraphic"/></feMerge></filter>`;
    h += `<filter id="fv-bloom-s" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur in="SourceGraphic" stdDeviation="3" result="b1"/><feGaussianBlur in="SourceGraphic" stdDeviation="9" result="b2"/><feMerge><feMergeNode in="b2"/><feMergeNode in="b1"/><feMergeNode in="SourceGraphic"/></feMerge></filter>`;
    /* electric arc: turbulence displacement (the seed is set per frame) + bloom */
    h += `<filter id="fv-zap" x="-30%" y="-30%" width="160%" height="160%"><feTurbulence id="fv-zap-n" type="turbulence" baseFrequency="0.09" numOctaves="2" seed="1" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="14" xChannelSelector="R" yChannelSelector="G" result="d"/><feGaussianBlur in="d" stdDeviation="4" result="g"/><feMerge><feMergeNode in="g"/><feMergeNode in="d"/></feMerge></filter>`;
    /* split-tone grade: teal shadows, orange highlights */
    h += `<filter id="fv-tealorange" color-interpolation-filters="sRGB"><feComponentTransfer><feFuncR type="table" tableValues="0.02 0.18 0.55 0.86 1"/><feFuncG type="table" tableValues="0.10 0.30 0.52 0.74 0.92"/><feFuncB type="table" tableValues="0.16 0.36 0.48 0.56 0.66"/></feComponentTransfer></filter>`;
    s.innerHTML = `<defs>${h}</defs>`;
    document.body.appendChild(s);
    DEFS = s;
    return s;
  };
  L.zapSeed = (f) => { const n = document.getElementById("fv-zap-n"); if (n) n.setAttribute("seed", String(1 + (f % 997))); };
  /* motion blur: stdDev = 3 k px. Peaks: text 6-12 px (k 2-4), full frame 15-20 px (k 5-6) */
  L.mbFilter = (v, max = 6) => { const k = Math.round(clamp(Math.abs(v), 0, max)); return k ? `url(#fv-mb${k})` : ""; };

  /* ---------------- textures ---------------- */
  const texCache = {};
  const loadImage = (url) => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error("image failed: " + String(url).slice(0, 80))); i.src = url; });
  const toBlobURL = (cv, type = "image/png", q) => new Promise((res) => cv.toBlob((b) => res(URL.createObjectURL(b)), type, q));
  const svgURL = (s) => "data:image/svg+xml;charset=utf-8," + encodeURIComponent(s);

  /* crumpled paper: two turbulence fields lit from the top-left, multiplied
     over a #C8C8C8 -> #707070 radial, then speckle, fibres and a vignette */
  async function paper(W, H, o = {}) {
    const seed = o.seed || 7;
    const sw = Math.round(W / 2), sh = Math.round(H / 2);
    const lit = `<svg xmlns="${SVGNS}" width="${sw}" height="${sh}" viewBox="0 0 ${sw} ${sh}">
      <filter id="p" x="0" y="0" width="100%" height="100%" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
        <feTurbulence type="turbulence" baseFrequency="${(0.0032 * 1080) / Math.min(W, H) * 2}" numOctaves="4" seed="${seed}" result="a"/>
        <feTurbulence type="fractalNoise" baseFrequency="${(0.011 * 1080) / Math.min(W, H) * 2}" numOctaves="3" seed="${seed + 3}" result="b"/>
        <feComposite in="a" in2="b" operator="arithmetic" k1="0" k2="0.9" k3="0.18" k4="0" result="h"/>
        <feDiffuseLighting in="h" surfaceScale="${o.relief || 7}" diffuseConstant="1.05" lighting-color="#ffffff" result="l"><feDistantLight azimuth="225" elevation="${o.elevation || 52}"/></feDiffuseLighting>
      </filter>
      <rect width="100%" height="100%" filter="url(#p)"/></svg>`;
    const img = await loadImage(svgURL(lit));
    const cv = document.createElement("canvas");
    cv.width = W; cv.height = H;
    const x = cv.getContext("2d", { willReadFrequently: true });
    const R = Math.hypot(W, H) / 2;
    const g = x.createRadialGradient(W / 2, H * 0.46, 0, W / 2, H * 0.46, R);
    g.addColorStop(0, o.c0 || "#C8C8C8"); g.addColorStop(0.55, o.c1 || "#B2B2B2"); g.addColorStop(1, o.c2 || "#707070");
    x.fillStyle = g; x.fillRect(0, 0, W, H);
    x.globalCompositeOperation = "multiply";
    x.globalAlpha = 1;
    x.drawImage(img, 0, 0, W, H);
    x.globalCompositeOperation = "soft-light";
    x.globalAlpha = 0.55;
    x.drawImage(img, 0, 0, W, H);
    x.globalCompositeOperation = "source-over";
    x.globalAlpha = 1;
    /* lift the result back to the brief's tone range (multiply darkens) */
    x.globalCompositeOperation = "screen";
    x.fillStyle = "rgba(70,70,70,1)"; x.fillRect(0, 0, W, H);
    x.globalCompositeOperation = "source-over";
    /* speckle + grain */
    const d = x.getImageData(0, 0, W, H), px = d.data, r = L.rng(seed * 131 + 9);
    for (let i = 0; i < px.length; i += 4) {
      let v = (r() - 0.5) * 16;
      const q = r();
      if (q < 0.0016) v -= 60 + r() * 60; else if (q < 0.0026) v += 40;
      px[i] = clamp(px[i] + v, 0, 255); px[i + 1] = clamp(px[i + 1] + v, 0, 255); px[i + 2] = clamp(px[i + 2] + v, 0, 255);
    }
    x.putImageData(d, 0, 0);
    /* crumple: faceted light/dark planes and long creases (a dark fold with a lit edge) */
    for (let k = 0; k < 70; k++) {
      const a = { x: r() * W, y: r() * H }, s = Math.min(W, H) * (0.18 + r() * 0.35);
      const b = { x: a.x + (r() - 0.5) * s * 2, y: a.y + (r() - 0.5) * s * 2 }, q = { x: a.x + (r() - 0.5) * s * 2, y: a.y + (r() - 0.5) * s * 2 };
      x.fillStyle = r() < 0.5 ? `rgba(255,255,255,${(0.025 + r() * 0.04).toFixed(3)})` : `rgba(0,0,0,${(0.025 + r() * 0.045).toFixed(3)})`;
      x.beginPath(); x.moveTo(a.x, a.y); x.lineTo(b.x, b.y); x.lineTo(q.x, q.y); x.closePath(); x.fill();
    }
    x.lineJoin = "round";
    for (let k = 0; k < (o.creases || 34); k++) {
      let px0 = r() * W, py0 = r() * H, an = r() * Math.PI * 2;
      const pts = [[px0, py0]], n = 3 + Math.floor(r() * 4), step = Math.min(W, H) * (0.06 + r() * 0.12);
      for (let i = 0; i < n; i++) { an += (r() - 0.5) * 0.9; px0 += Math.cos(an) * step; py0 += Math.sin(an) * step; pts.push([px0, py0]); }
      const line = (dx, dy) => { x.beginPath(); x.moveTo(pts[0][0] + dx, pts[0][1] + dy); for (const [a, b] of pts.slice(1)) x.lineTo(a + dx, b + dy); x.stroke(); };
      const w0 = 0.8 + r() * 1.4;
      x.lineWidth = w0 * 4; x.strokeStyle = "rgba(0,0,0,.045)"; line(1.5, 1.5);
      x.lineWidth = w0; x.strokeStyle = "rgba(0,0,0,.11)"; line(0, 0);
      x.lineWidth = w0 * 1.6; x.strokeStyle = "rgba(255,255,255,.13)"; line(-2, -2);
    }
    /* a few fibres */
    x.strokeStyle = "rgba(40,40,40,.10)"; x.lineWidth = 1;
    for (let k = 0; k < 90; k++) { const a = r() * W, b = r() * H, l = 6 + r() * 22, an = r() * Math.PI; x.beginPath(); x.moveTo(a, b); x.quadraticCurveTo(a + Math.cos(an) * l * 0.5 + r() * 4, b + Math.sin(an) * l * 0.5, a + Math.cos(an) * l, b + Math.sin(an) * l); x.stroke(); }
    const v = x.createRadialGradient(W / 2, H * 0.46, Math.min(W, H) * 0.32, W / 2, H * 0.46, R);
    v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(1, `rgba(0,0,0,${o.vignette != null ? o.vignette : 0.35})`);
    x.fillStyle = v; x.fillRect(0, 0, W, H);
    return toBlobURL(cv, "image/jpeg", 0.93);
  }

  L.texture = (kind, W, H, o = {}) => {
    const key = `${kind}|${W}|${H}|${JSON.stringify(o)}`;
    if (!texCache[key]) texCache[key] = kind === "paper" ? paper(W, H, o) : Promise.resolve("");
    return texCache[key];
  };

  /* CSS for the lightweight textures (grid, blueprint, grain, clean) */
  L.textureCSS = (kind, C) => {
    if (kind === "grid") return `background-color:${C.bg};background-image:linear-gradient(${L.hexA(C.ink, 0.07)} 1px, transparent 1px),linear-gradient(90deg, ${L.hexA(C.ink, 0.07)} 1px, transparent 1px);background-size:24px 24px`;
    if (kind === "blueprint") return "background-color:#0f3a5f;background-image:linear-gradient(rgba(255,255,255,.16) 1px, transparent 1px),linear-gradient(90deg, rgba(255,255,255,.16) 1px, transparent 1px),linear-gradient(rgba(255,255,255,.07) 1px, transparent 1px),linear-gradient(90deg, rgba(255,255,255,.07) 1px, transparent 1px);background-size:120px 120px,120px 120px,24px 24px,24px 24px";
    /* theme textures (config/themes.yaml): all pure CSS, no fetched files */
    if (kind === "halftone") return `background-color:${C.bg};background-image:radial-gradient(${L.hexA(C.ink, 0.16)} 22%, transparent 24%),radial-gradient(${L.hexA(C.ink, 0.1)} 22%, transparent 24%);background-size:22px 22px;background-position:0 0,11px 11px`;
    if (kind === "scanlines") return `background-color:${C.bg};background-image:repeating-linear-gradient(0deg, ${L.hexA(C.ink, 0.07)} 0 2px, transparent 2px 5px),radial-gradient(ellipse at 50% 40%, ${L.hexA(C.accent, 0.12)}, transparent 65%)`;
    if (kind === "notebook") return `background-color:${C.bg};background-image:linear-gradient(${L.hexA(C.accent2 || C.accent, 0.28)} 1px, transparent 1px),linear-gradient(90deg, transparent 94px, ${L.hexA(C.accent, 0.35)} 94px 96px, transparent 96px);background-size:100% 56px,100% 100%`;
    if (kind === "dots") return `background-color:${C.bg};background-image:radial-gradient(${L.hexA(C.ink, 0.18)} 2.5px, transparent 3px);background-size:34px 34px`;
    if (kind === "sunburst") return `background-color:${C.bg};background-image:repeating-conic-gradient(from 0deg at 50% 42%, ${L.hexA(C.accent, 0.13)} 0deg 6deg, transparent 6deg 15deg)`;
    if (kind === "stripes") return `background-color:${C.bg};background-image:repeating-linear-gradient(135deg, ${L.hexA(C.ink, 0.06)} 0 28px, transparent 28px 56px)`;
    if (kind === "film") return `background-color:${C.bg};background-image:radial-gradient(ellipse at 50% 45%, ${L.hexA(C.surface, 0.9)}, transparent 70%),repeating-linear-gradient(90deg, ${L.hexA(C.ink, 0.035)} 0 1px, transparent 1px 7px)`;
    return `background:${C.bg}`;
  };
  L.TEXTURES_CSS = ["grid", "blueprint", "halftone", "scanlines", "notebook", "dots", "sunburst", "stripes", "film"];

  /* ---------------- image treatments ---------------- */
  const fxCache = {};
  /* o: {bw, halftone, cell, contrast, bright, ink, paperTone, mix, max, angle} */
  async function treat(url, o) {
    const img = await loadImage(url);
    let w = img.naturalWidth || img.width || 800, h = img.naturalHeight || img.height || 800;
    const max = o.max || 1400, k = Math.min(1, max / Math.max(w, h));
    /* SVGs without intrinsic size scale up to max */
    if (/\.svg($|\?)/i.test(url)) { const s = max / Math.max(w, h); w *= s; h *= s; } else { w *= k; h *= k; }
    w = Math.max(1, Math.round(w)); h = Math.max(1, Math.round(h));
    const src = document.createElement("canvas"); src.width = w; src.height = h;
    const sx = src.getContext("2d", { willReadFrequently: true });
    sx.drawImage(img, 0, 0, w, h);
    const d = sx.getImageData(0, 0, w, h), px = d.data;
    const con = o.contrast != null ? o.contrast : 1.25, br = o.bright || 0;
    const lum = new Float32Array(w * h);
    for (let i = 0, j = 0; i < px.length; i += 4, j++) {
      let v = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2];
      v = clamp((v - 128) * con + 128 + br, 0, 255);
      lum[j] = v;
      if (o.bw || o.halftone) { px[i] = px[i + 1] = px[i + 2] = v; }
    }
    sx.putImageData(d, 0, 0);
    if (!o.halftone) return toBlobURL(src);
    /* halftone: dots on a 45 deg screen, radius from local darkness, over a light tone of the photo */
    const out = document.createElement("canvas"); out.width = w; out.height = h;
    const x = out.getContext("2d", { willReadFrequently: true });
    x.globalAlpha = o.mix != null ? o.mix : 0.55;
    x.drawImage(src, 0, 0);
    x.globalAlpha = 1;
    x.globalCompositeOperation = "screen";
    x.fillStyle = `rgba(255,255,255,${o.lift != null ? o.lift : 0.28})`; x.fillRect(0, 0, w, h);
    x.globalCompositeOperation = "source-over";
    const cell = o.cell || Math.max(5, Math.round(Math.max(w, h) / 120));
    const an = ((o.angle != null ? o.angle : 45) * Math.PI) / 180, ca = Math.cos(an), sa = Math.sin(an);
    const D = Math.hypot(w, h) / 2, cxm = w / 2, cym = h / 2;
    x.fillStyle = o.ink || "#141414";
    const sample = (X, Y) => {
      let s = 0, n = 0;
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        const xx = clamp(Math.round(X + dx * cell * 0.3), 0, w - 1), yy = clamp(Math.round(Y + dy * cell * 0.3), 0, h - 1);
        s += lum[yy * w + xx]; n++;
      }
      return s / n;
    };
    for (let v = -D; v <= D; v += cell) {
      for (let u = -D; u <= D; u += cell) {
        const X = cxm + u * ca - v * sa, Y = cym + u * sa + v * ca;
        if (X < -cell || Y < -cell || X > w + cell || Y > h + cell) continue;
        const dk = 1 - sample(X, Y) / 255;
        const r = cell * 0.5 * Math.sqrt(dk) * 1.18;
        if (r < 0.35) continue;
        x.beginPath(); x.arc(X, Y, r, 0, Math.PI * 2); x.fill();
      }
    }
    /* keep the cut-out's alpha */
    x.globalCompositeOperation = "destination-in";
    x.drawImage(img, 0, 0, w, h);
    return toBlobURL(out);
  }
  L.treat = (url, o = {}) => {
    const key = url + "|" + JSON.stringify(o);
    if (!fxCache[key]) fxCache[key] = treat(url, o).catch((e) => { console.warn(e.message); return url; });
    return fxCache[key];
  };
  /* L.setImg for treated images. fx = null -> plain setImg */
  const fxOf = new WeakMap();
  L.setImgFx = (img, url, fx) => {
    if (!fx || (!fx.bw && !fx.halftone)) return L.setImg(img, url);
    const key = url + "|" + JSON.stringify(fx);
    if (fxOf.get(img) === key) return;
    fxOf.set(img, key);
    L.pending.push(L.treat(url, fx).then((u) => { img.src = u; return img.decode().catch(() => {}); }));
  };
  L.projUrl = (src) => (/^(data:|blob:|https?:|\/)/.test(String(src)) ? String(src) : "/project/" + String(src || "").replace(/^\.?\/+/, ""));

  /* The opaque bbox + a coarse occupancy mask of an image, measured once per url
     (alpha > 16 on a fixed-size canvas, so it is deterministic). All values are
     fractions of the image. L.measureCut preloads; L.cutInfo reads synchronously. */
  const cutCache = {}, cutDone = {};
  L.measureCut = (url) => {
    if (cutCache[url]) return cutCache[url];
    return (cutCache[url] = loadImage(url).then((img) => {
      const nw = img.naturalWidth || 800, nh = img.naturalHeight || 800;
      const k = Math.min(1, 256 / Math.max(nw, nh)), cw = Math.max(1, Math.round(nw * k)), ch = Math.max(1, Math.round(nh * k));
      const cv = document.createElement("canvas"); cv.width = cw; cv.height = ch;
      const x = cv.getContext("2d", { willReadFrequently: true });
      x.drawImage(img, 0, 0, cw, ch);
      const a = x.getImageData(0, 0, cw, ch).data;
      let x0 = cw, y0 = ch, x1 = -1, y1 = -1;
      const mask = new Uint8Array(cw * ch);
      for (let j = 0; j < ch; j++) for (let i = 0; i < cw; i++) if (a[(j * cw + i) * 4 + 3] > 16) { mask[j * cw + i] = 1; if (i < x0) x0 = i; if (i > x1) x1 = i; if (j < y0) y0 = j; if (j > y1) y1 = j; }
      if (x1 < 0) { x0 = y0 = 0; x1 = cw - 1; y1 = ch - 1; mask.fill(1); }
      return (cutDone[url] = { nw, nh, x: x0 / cw, y: y0 / ch, w: (x1 - x0 + 1) / cw, h: (y1 - y0 + 1) / ch, mask, cw, ch });
    }).catch(() => null));
  };
  L.cutInfo = (url) => cutDone[url] || null;
  /* every cut-out named anywhere in a scene's params */
  L.cutSources = (o, out = []) => {
    if (Array.isArray(o)) o.forEach((v) => L.cutSources(v, out));
    else if (o && typeof o === "object") { if (o.src && o.kind === "cutout") out.push(L.projUrl(o.src)); for (const k in o) L.cutSources(o[k], out); }
    return out;
  };
  /* is this #rrggbb a dark colour? */
  L.isDark = (hex) => { const m = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim()); if (!m) return false; const n = parseInt(m[1], 16); return 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255) < 110; };
  /* readable ink for a scene: the theme's ink if it reads on that ground, else plain black or white */
  L.inkOn = (dark) => (dark ? (L.isDark(L.C.ink) ? "#f5f5f5" : L.C.ink) : (L.isDark(L.C.ink) ? L.C.ink : "#111111"));
  /* mix two #rrggbb colours */
  L.mix = (a, b, k) => {
    const pa = /^#?([0-9a-f]{6})$/i.exec(String(a).trim()), pb = /^#?([0-9a-f]{6})$/i.exec(String(b).trim());
    if (!pa || !pb) return a;
    const na = parseInt(pa[1], 16), nb = parseInt(pb[1], 16), ch = (s) => Math.round(((na >> s) & 255) * (1 - k) + ((nb >> s) & 255) * k);
    return `rgb(${ch(16)},${ch(8)},${ch(0)})`;
  };

  /* outline (for transparent cut-outs) + contact shadow (key light top-left) */
  L.cutFilter = (o = {}) => {
    const out = [];
    const w = o.outline === false ? 0 : o.outline || 0;
    const col = o.color || "#ffffff";
    if (w) out.push(`drop-shadow(${w}px 0 0 ${col})`, `drop-shadow(-${w}px 0 0 ${col})`, `drop-shadow(0 ${w}px 0 ${col})`, `drop-shadow(0 -${w}px 0 ${col})`);
    if (o.shadow !== false) { const s = o.shadow || {}; out.push(`drop-shadow(${s.x != null ? s.x : 14}px ${s.y != null ? s.y : 18}px ${s.blur != null ? s.blur : 24}px rgba(0,0,0,${s.a != null ? s.a : 0.45}))`); }
    return out.join(" ");
  };

  /* ---------------- shapes ---------------- */
  L.chamfer = (w, h, c, ox = 0, oy = 0) => {
    c = Math.min(c, w / 2, h / 2);
    return [[c, 0], [w - c, 0], [w, c], [w, h - c], [w - c, h], [c, h], [0, h - c], [0, c]].map(([a, b]) => `${(a + ox).toFixed(1)},${(b + oy).toFixed(1)}`).join(" ");
  };
  L.chamferClip = (w, h, c) => `polygon(${L.chamfer(w, h, c).split(" ").map((p) => p.split(",").map((v) => v + "px").join(" ")).join(",")})`;

  /* 24x24 stroke icons */
  const ICONS = {
    bell: "M6 16V11a6 6 0 0 1 12 0v5l2 2H4z M10 20a2 2 0 0 0 4 0",
    flame: "M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-3 2-4 2-7 1.5 1 2 2.5 2 4 1-2 1-4 1-7z",
    gear: "M12 8.5a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7z M12 2v3 M12 19v3 M2 12h3 M19 12h3 M4.9 4.9l2.1 2.1 M17 17l2.1 2.1 M4.9 19.1L7 17 M17 7l2.1-2.1",
    star: "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z",
    check: "M4 12.5l5 5L20 6.5",
    bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
    heart: "M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.5-7 10-7 10z",
    clock: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z M12 7v5l3 2",
    target: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z M12 7.5a4.5 4.5 0 1 0 0 9a4.5 4.5 0 1 0 0-9z M12 11.2a.8.8 0 1 0 0 1.6a.8.8 0 1 0 0-1.6z",
    user: "M12 4a4 4 0 1 0 0 8a4 4 0 1 0 0-8z M4 21c1-4.5 4-6.5 8-6.5s7 2 8 6.5",
    phone: "M8 2.5h8a1.5 1.5 0 0 1 1.5 1.5v16a1.5 1.5 0 0 1-1.5 1.5H8A1.5 1.5 0 0 1 6.5 20V4A1.5 1.5 0 0 1 8 2.5z M11 18.5h2",
    chart: "M4 20V4 M4 20h16 M8 16v-4 M12 16V8 M16 16v-6",
    lock: "M6 11h12v9H6z M8.5 11V8a3.5 3.5 0 0 1 7 0v3",
    repeat: "M4 11V9a3 3 0 0 1 3-3h12 M16 3l3 3-3 3 M20 13v2a3 3 0 0 1-3 3H5 M8 21l-3-3 3-3",
    trophy: "M8 4h8v5a4 4 0 0 1-8 0z M8 6H5a3 3 0 0 0 3 4 M16 6h3a3 3 0 0 1-3 4 M12 13v4 M8.5 20h7 M10 17h4v3h-4z",
    coffee: "M5 9h11v5a5 5 0 0 1-5 5h-1a5 5 0 0 1-5-5z M16 10h1.5a2.5 2.5 0 0 1 0 5H16 M8 3c0 1.5 1 1.5 1 3 M12 3c0 1.5 1 1.5 1 3",
    book: "M4 5a2 2 0 0 1 2-2h13v15H6a2 2 0 0 0-2 2z M4 20a2 2 0 0 0 2 2h13v-4",
    sun: "M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8z M12 2v2 M12 20v2 M2 12h2 M20 12h2 M4.9 4.9l1.4 1.4 M17.7 17.7l1.4 1.4 M4.9 19.1l1.4-1.4 M17.7 6.3l1.4-1.4",
    brain: "M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 5 2V5a2.5 2.5 0 0 0-2-1z M15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-5 2V5a2.5 2.5 0 0 1 2-1z",
    spark: "M12 2v6 M12 16v6 M2 12h6 M16 12h6 M5 5l3.5 3.5 M15.5 15.5L19 19 M5 19l3.5-3.5 M15.5 8.5L19 5",
    arrow: "M5 12h14 M13 6l6 6-6 6",
    up: "M12 20V4 M6 10l6-6 6 6",
    play: "M8 5v14l11-7z",
  };
  L.ICONS = ICONS;
  L.icon = (name, size = 48, color = "currentColor", sw = 2) => {
    const d = ICONS[name];
    if (!d) return `<span style="font:900 ${size * 0.62}px/1 var(--sans);color:${color}">${L.esc(String(name || "").slice(0, 3))}</span>`;
    return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
  };

  /* a hand-drawn curved arrow from a to b (stage px) inside an <svg>.
     bend: signed fraction of the length pushing the control point sideways. */
  L.handArrow = (svgParent, a, b, o = {}) => {
    const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
    const bend = o.bend != null ? o.bend : 0.3;
    const mx = (a.x + b.x) / 2 - (dy / len) * len * bend, my = (a.y + b.y) / 2 + (dx / len) * len * bend;
    /* tangent at the end of the quadratic */
    const tx = b.x - mx, ty = b.y - my, tl = Math.hypot(tx, ty) || 1;
    const hs = o.head || 26, ux = tx / tl, uy = ty / tl;
    const h1 = { x: b.x - ux * hs - uy * hs * 0.55, y: b.y - uy * hs + ux * hs * 0.55 };
    const h2 = { x: b.x - ux * hs + uy * hs * 0.55, y: b.y - uy * hs - ux * hs * 0.55 };
    const d = `M${a.x.toFixed(1)} ${a.y.toFixed(1)} Q${mx.toFixed(1)} ${my.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)} M${h1.x.toFixed(1)} ${h1.y.toFixed(1)} L${b.x.toFixed(1)} ${b.y.toFixed(1)} L${h2.x.toFixed(1)} ${h2.y.toFixed(1)}`;
    return L.rough(svgParent, "path", [d], { stroke: o.color || "#111", strokeWidth: o.width || 4.2, roughness: o.roughness != null ? o.roughness : 0.9, bowing: 0.6, seed: o.seed || 3, disableMultiStroke: !!o.single });
  };

  /* ---------------- backgrounds ---------------- */
  L.paperBg = (root, c, o = {}) => {
    const img = el("img", "abs fv-bgimg", root);
    L.pos(img, 0, 0, c.W, c.H);
    L.pending.push(L.texture("paper", c.W, c.H, o).then((u) => { if (u) { img.src = u; return img.decode().catch(() => {}); } }));
    return img;
  };
  L.studioBg = (root, c) => {
    const b = el("div", "abs", root);
    L.pos(b, 0, 0, c.W, c.H);
    b.style.background = "radial-gradient(ellipse 75% 60% at 50% 42%, #F4F4F4 0%, #ECECEC 45%, #D9D9D9 100%)";
    return b;
  };
  /* #111 with a 24 px grid, drifting dust and a vignette. returns {node, at(t)} */
  L.darkBg = (root, c, o = {}) => {
    const b = el("div", "abs fv-dark", root);
    L.pos(b, 0, 0, c.W, c.H);
    b.style.background = o.color || "#111111";
    if (o.grid !== false) {
      const g = el("div", "abs", b);
      L.pos(g, 0, 0, c.W, c.H);
      const s = o.grid || 24;
      g.style.cssText += `;opacity:.35;background-image:linear-gradient(#2A2A2A 1px, transparent 1px),linear-gradient(90deg, #2A2A2A 1px, transparent 1px);background-size:${s}px ${s}px;background-position:${(c.W / 2) % s}px ${(c.H / 2) % s}px`;
    }
    const dust = el("div", "abs", b);
    L.pos(dust, 0, 0, c.W, c.H);
    const r = L.rng(o.seed || 77);
    const motes = Array.from({ length: o.dust != null ? o.dust : 60 }, () => ({ x: r() * c.W, y: r() * c.H, s: 1 + r() * 2.6, vx: (r() - 0.5) * 14, vy: -4 - r() * 12, a: 0.15 + r() * 0.45, ph: r() * 6.28 }));
    const v = el("div", "abs", b);
    L.pos(v, 0, 0, c.W, c.H);
    v.style.background = "radial-gradient(ellipse 80% 70% at 50% 45%, transparent 45%, rgba(0,0,0,.65) 100%)";
    return {
      node: b,
      at(t) {
        dust.innerHTML = motes.map((m) => {
          const x = ((m.x + m.vx * t) % c.W + c.W) % c.W, y = ((m.y + m.vy * t) % c.H + c.H) % c.H;
          const a = m.a * (0.6 + 0.4 * Math.sin(t * 1.7 + m.ph));
          return `<i style="position:absolute;left:${x.toFixed(1)}px;top:${y.toFixed(1)}px;width:${m.s.toFixed(1)}px;height:${m.s.toFixed(1)}px;border-radius:50%;background:#fff;opacity:${a.toFixed(3)}"></i>`;
        }).join("");
      },
    };
  };
  /* deterministic starfield: {node, at(t, z)} z = zoom-through speed */
  L.stars = (root, c, n = 140, seed = 5) => {
    const s = el("div", "abs", root);
    L.pos(s, 0, 0, c.W, c.H);
    const r = L.rng(seed);
    const st = Array.from({ length: n }, () => ({ a: r() * 6.283, d: 0.05 + r() * 0.95, s: 0.6 + r() * 2.2, ph: r() * 6.28, w: 1 + r() * 3 }));
    const R = Math.hypot(c.W, c.H) / 2;
    return {
      node: s,
      at(t, fly = 0) {
        s.innerHTML = st.map((q) => {
          const d = ((q.d + fly) % 1 + 1) % 1;
          const rr = Math.pow(d, 1.6) * R;
          const x = c.W / 2 + Math.cos(q.a) * rr, y = c.H / 2 + Math.sin(q.a) * rr;
          const a = (0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * q.w + q.ph))) * clamp(d * 4);
          const sz = q.s * (0.6 + d);
          return `<i style="position:absolute;left:${x.toFixed(1)}px;top:${y.toFixed(1)}px;width:${sz.toFixed(1)}px;height:${sz.toFixed(1)}px;border-radius:50%;background:#fff;box-shadow:0 0 ${(sz * 3).toFixed(1)}px rgba(255,255,255,.8);opacity:${a.toFixed(3)}"></i>`;
        }).join("");
      },
    };
  };

  /* ---------------- kinetic type ---------------- */
  const splitWords = (parent, text, cls, wrapCls) => {
    const node = el("div", cls || "", parent);
    const spans = [];
    String(text).split("\n").forEach((line, li) => {
      if (li) node.appendChild(document.createElement("br"));
      let inAcc = false;
      line.split(/\s+/).filter(Boolean).forEach((w, k) => {
        if (k) node.appendChild(document.createTextNode(" "));
        /* *one word* or *a few words* */
        const opens = w.startsWith("*"), closes = /\*[.,!?:;]*$/.test(w);
        if (opens) inAcc = true;
        const acc = inAcc;
        if (closes) inAcc = false;
        const s = el("span", wrapCls + (acc ? " acc" : ""), node, L.esc(w.replace(/\*/g, "")));
        s.style.display = "inline-block";
        spans.push(s);
      });
    });
    return { node, spans };
  };
  /* big title words sliding in from the side with a motion-blur trail */
  L.slideWords = (parent, text, cls, o = {}) => {
    const { node, spans } = splitWords(parent, text, cls, "fv-sw");
    const dist = o.dist || 520, stag = o.stagger != null ? o.stagger : 0.09, dur = o.dur || 0.55, dir = o.dir || 1;
    const X = (t, t0) => (1 - L.expo(seg(t, t0, t0 + dur))) * dist * dir;
    return {
      node, spans,
      at(t, t0) {
        spans.forEach((s, k) => {
          const a = t0 + k * stag;
          const x = X(t, a), v = (X(t - 1 / 30, a) - x);
          s.style.opacity = t >= a ? 1 : 0;
          s.style.transform = `translateX(${x.toFixed(1)}px) skewX(${clamp(-v * 0.25 * dir, -14, 14).toFixed(2)}deg)`;
          s.style.filter = L.mbFilter(v / 10, 4);
        });
      },
    };
  };
  /* title reveal: per word, blur 6 px -> 0 and opacity 0 -> 1 in 0.13 s, 0.067 s apart,
     with a small expo rise. at(t, t0, when) : when(k, dflt) optionally overrides a word's start. */
  L.revealWords = (parent, text, cls, o = {}) => {
    const { node, spans } = splitWords(parent, text, cls, "fv-sw");
    const dur = o.dur || L.TIMING.revealDur, gap = o.gap != null ? o.gap : L.TIMING.revealGap, rise = o.rise != null ? o.rise : 22;
    const rots = spans.map((s, k) => (o.tilt ? (k % 2 ? 1 : -1) * o.tilt * (0.5 + 0.5 * L.rng(31 + k * 7)()) : 0));
    return {
      node, spans,
      at(t, t0, when) {
        spans.forEach((s, k) => {
          const a = when ? when(k, t0 + k * gap) : t0 + k * gap;
          const q = seg(t, a, a + dur), e = L.EASE.arrive(seg(t, a, a + dur * 2.4));
          s.style.opacity = q;
          s.style.visibility = q > 0 ? "visible" : "hidden";
          s.style.filter = q < 1 ? `blur(${((1 - q) * 6).toFixed(2)}px)` : "";
          s.style.transform = `translateY(${((1 - e) * rise).toFixed(2)}px) rotate(${rots[k].toFixed(2)}deg)`;
        });
      },
    };
  };
  /* subtitle words: scale 0.8 -> 1 + 4 px blur fade over ~5 frames, staggered 6 frames */
  L.subWords = (parent, text, cls) => {
    const { node, spans } = splitWords(parent, text, cls, "fv-sub");
    return {
      node, spans,
      at(t, t0, fps = 30) {
        spans.forEach((s, k) => {
          const p = eo(seg(t, t0 + (k * 6) / fps, t0 + (k * 6 + 5) / fps));
          s.style.opacity = p;
          s.style.transform = `scale(${(0.8 + 0.2 * p).toFixed(4)})`;
          s.style.filter = p < 1 ? `blur(${((1 - p) * 4).toFixed(2)}px)` : "";
        });
      },
      end(t0, fps = 30) { return t0 + ((spans.length - 1) * 6 + 5) / fps; },
    };
  };
  /* entrance: scale 0.9 -> 1 (back-out) + blur-to-sharp */
  L.resolveIn = (e, t, t0, d = 0.55, o = {}) => {
    const q = seg(t, t0, t0 + d);
    const f0 = o.from != null ? o.from : 0.9;
    const s = f0 + (1 - f0) * (o.spring ? L.spring(t - t0, o.spring) : o.expo ? L.expo(q) : L.back(q, 1.4));
    const b = (1 - eo(q)) * (o.blur != null ? o.blur : 10);
    e.style.opacity = clamp(q * 3);
    e.style.visibility = q > 0 ? "visible" : "hidden";
    e.style.transform = (o.pre || "") + ` scale(${s.toFixed(4)})` + (o.post || "");
    e.style.filter = (b > 0.05 ? `blur(${b.toFixed(2)}px) ` : "") + (o.filter || "");
    return q;
  };

  /* slow camera drift: push 1.0 -> to, plus a gentle bob */
  L.drift = (t, dur, o = {}) => {
    const z = 1 + ((o.to != null ? o.to : 1.08) - 1) * L.eio(clamp(t / Math.max(0.1, dur)));
    const y = Math.sin((t / (o.period || 3.4)) * Math.PI * 2) * (o.bob != null ? o.bob : 5);
    const x = Math.sin((t / ((o.period || 3.4) * 1.7)) * Math.PI * 2) * (o.bob != null ? o.bob : 5) * 0.6;
    return `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px) scale(${z.toFixed(5)})`;
  };

  /* neon text */
  L.neon = (e, color) => { e.style.color = "#fff"; e.style.textShadow = `0 0 6px ${color}, 0 0 20px ${L.hexA(color, 0.6)}, 0 0 2px #fff`; };

  /* density of sound cues: rich | standard | minimal */
  L.sfxLevel = (c) => ({ rich: 1, standard: 2, minimal: 3 }[(c.p && c.p.sfx) || c.sfx || "standard"] || 2);
})();
