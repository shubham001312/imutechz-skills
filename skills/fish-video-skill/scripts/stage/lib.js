/* Stage library: timing, easing, kinetic type, hand-drawn strokes, the
   browser window with camera + cursor, logo, grain.

   THE RULE: everything is a pure function of time. renderAt(t) may be
   called for any t, in any order, by any of several parallel workers, and
   must draw the same frame. No Math.random (use L.rng(seed)), no Date, no
   CSS transitions/animations, no requestAnimationFrame. */
(function () {
  "use strict";
  const L = (window.L = {});

  /* palette — overwritten from timeline.theme in L.applyTheme */
  L.C = {
    bg: "#f3ede2", surface: "#faf7f0", paper: "#f8f4ec", ink: "#1a1714", fg: "#1c1915",
    muted: "#58524a", dim: "#847c70", line: "rgba(28,25,20,.12)", line2: "rgba(28,25,20,.24)",
    accent: "#d9481e", accent2: "#15858d", ok: "#1f8a46", dark: "#12100d", darkFg: "#f2ece0",
  };
  L.BPM = 120;
  L.BEAT = 0.5;
  L.BAR = 2;
  L.FPS = 30;
  L.setTempo = (bpm, beatsPerBar = 4) => { L.BPM = bpm; L.BEAT = 60 / bpm; L.BAR = L.BEAT * beatsPerBar; };

  const hexA = (hex, a) => {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim());
    if (!m) return hex;
    const n = parseInt(m[1], 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  };
  L.hexA = hexA;

  /** Apply a design system: {colors:{...}, fonts:{sans,display,serif,mono,hand}, mode} */
  L.applyTheme = (th = {}) => {
    /* mutate in place: scenes destructure L.C at load time */
    const c = Object.assign(L.C, th.colors || {});
    if (!th.colors || !th.colors.line) c.line = hexA(c.ink, 0.12);
    if (!th.colors || !th.colors.line2) c.line2 = hexA(c.ink, 0.24);
    c.accentSoft = hexA(c.accent, 0.14);
    const r = document.documentElement.style;
    const map = { bg: "--bg", surface: "--surface", paper: "--paper", ink: "--ink", fg: "--fg", muted: "--muted", dim: "--dim", line: "--line", line2: "--line2", accent: "--accent", accent2: "--accent2", accentSoft: "--accent-soft", ok: "--ok", dark: "--dark", darkFg: "--dark-fg" };
    for (const k in map) if (c[k]) r.setProperty(map[k], c[k]);
    const f = th.fonts || {};
    const stack = (name, fb) => (name ? `"${name}", ${fb}` : null);
    if (f.sans) r.setProperty("--sans", stack(f.sans, '"Noto Sans Devanagari", system-ui, sans-serif'));
    if (f.display) r.setProperty("--display", stack(f.display, "var(--sans)"));
    if (f.serif) r.setProperty("--serif", stack(f.serif, "Georgia, serif"));
    if (f.mono) r.setProperty("--mono", stack(f.mono, "ui-monospace, monospace"));
    if (f.hand) r.setProperty("--hand", stack(f.hand, "cursive"));
    if (th.mode === "dark") document.documentElement.classList.add("theme-dark");
    /* theme layout + motion tokens (config/themes.yaml). Scenes read L.T; the defaults reproduce the classic look. */
    L.T = Object.assign({ radius: 22, border: 3, kicker: "chip", card: "panel", caps: false, weight: 900, track: -0.02, shadow: "soft", rise: 1, speed: 1, push: 1, align: "center", scrim: 0.55, dim: 0.45 }, th.layout || {});
    const cap = th.captions || {};
    const cv = { "--cap-fill": cap.fill, "--cap-stroke": cap.stroke, "--cap-stroke-w": cap.stroke_w, "--cap-shadow": cap.shadow, "--cap-plate": cap.plate, "--cap-case": cap.case, "--cap-radius": cap.radius };
    for (const k in cv) if (cv[k] != null) r.setProperty(k, cv[k]);
  };
  L.T = { radius: 22, border: 3, kicker: "chip", card: "panel", caps: false, weight: 900, track: -0.02, shadow: "soft", rise: 1, speed: 1, push: 1, align: "center", scrim: 0.55, dim: 0.45 };

  /* ---------------- maths ---------------- */
  const clamp = (L.clamp = (v, a = 0, b = 1) => (v < a ? a : v > b ? b : v));
  L.lerp = (a, b, t) => a + (b - a) * t;
  L.seg = (t, a, b) => (b <= a ? (t >= b ? 1 : 0) : clamp((t - a) / (b - a)));
  L.eo = (t) => 1 - Math.pow(1 - clamp(t), 3);
  L.ei = (t) => Math.pow(clamp(t), 3);
  L.eio = (t) => { t = clamp(t); return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
  L.expo = (t) => { t = clamp(t); return t === 1 ? 1 : 1 - Math.pow(2, -10 * t); };
  L.back = (t, s = 1.70158) => { t = clamp(t); return 1 + (s + 1) * Math.pow(t - 1, 3) + s * Math.pow(t - 1, 2); };
  L.inout = (t, a, d, b, d2) => Math.min(L.eo(L.seg(t, a, a + d)), 1 - L.ei(L.seg(t, b - (d2 || d), b)));
  /* Easing by role (references/scene-catalogue.md, Motion rules). */
  const pow2io = (t) => { t = clamp(t); return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; };
  const pow4o = (t) => 1 - Math.pow(1 - clamp(t), 4);
  L.EASE = {
    arrive: L.expo,       /* expo.out: things landing */
    arrive2: pow4o,       /* power4.out: heavier landings */
    camera: pow2io,       /* power2.inOut: camera moves */
    flood: pow2io,        /* power2.inOut: colour floods */
    exit: L.ei,           /* power3.in: exits */
    through: L.ei,        /* power3.in: zoom-throughs */
    linear: (t) => clamp(t), /* rotation and progress only */
  };
  /* Analytic damped spring, 0 -> 1 (deterministic at any fps):
     x(t) = 1 - e^(-zeta w0 t) (cos(w1 t) + (zeta w0 / w1) sin(w1 t)),
     w0 = sqrt(k/m), zeta = c / (2 sqrt(k m)), w1 = w0 sqrt(1 - zeta^2). */
  L.spring = (t, o = {}) => {
    if (t <= 0) return 0;
    const k = o.stiffness != null ? o.stiffness : 100, m = o.mass != null ? o.mass : 1, c = o.damping != null ? o.damping : 10;
    const w0 = Math.sqrt(k / m), z = c / (2 * Math.sqrt(k * m));
    if (z >= 1) { /* critically / over damped */
      if (z === 1) return 1 - Math.exp(-w0 * t) * (1 + w0 * t);
      const s = w0 * Math.sqrt(z * z - 1), r1 = -z * w0 + s, r2 = -z * w0 - s;
      return 1 - (r2 * Math.exp(r1 * t) - r1 * Math.exp(r2 * t)) / (r2 - r1);
    }
    const w1 = w0 * Math.sqrt(1 - z * z);
    return 1 - Math.exp(-z * w0 * t) * (Math.cos(w1 * t) + ((z * w0) / w1) * Math.sin(w1 * t));
  };
  /* zeta 0.7-0.85 for premium arrivals, 0.4-0.6 for playful pops */
  L.SPRING = { premium: { stiffness: 120, mass: 1, damping: 17.5 }, playful: { stiffness: 190, mass: 1, damping: 14 } };
  /* a decaying nudge: 0 at d = 0, rings out in about 0.5 s */
  L.punch = (d, f = 13, k = 6) => (d <= 0 ? 0 : Math.exp(-k * d) * Math.sin(f * d));
  /* reading hold for n on-screen words */
  L.readHold = (n) => 0.5 + 0.3 * n;
  L.TIMING = { fast: [0.3, 0.6], exitRatio: 0.55, overlap: [0.3, 0.5], staggerWord: [0.06, 0.12], staggerItem: [0.04, 0.08], revealDur: 0.13, revealGap: 0.067 };

  /* Pop-caption groups. limit: words per group by delivery (2-3 high energy,
     3-5 conversational, 4-6 calm). A group breaks at a sentence end, at a gap of
     150 ms or more, or at the word limit; it opens at its first word and closes
     at or after its last word, never into the next group. Words stay in spoken order. */
  L.capLimit = (delivery) => {
    const d = String(delivery || "").toLowerCase();
    if (/punch|energ|hype|fast|high/.test(d)) return 3;
    if (/calm|slow|soft|narrat|documentary/.test(d)) return 6;
    return 5;
  };
  const WEAK = /^(the|a|an|of|to|and|or|but|in|on|at|for|with|your|my|so)$/i;
  L.capGroups = (words, delivery, o = {}) => {
    const limit = o.limit || L.capLimit(delivery), gap = o.gap != null ? o.gap : 0.15, hold = o.hold != null ? o.hold : 0.3;
    const g = [];
    let cur = [];
    const flush = () => { if (cur.length) { g.push(cur); cur = []; } };
    for (const w of words || []) {
      if (cur.length && w.t0 - cur[cur.length - 1].t1 >= gap) {
        /* a pause never strands a connecting word: "and" alone is not a caption; it travels to the phrase it belongs to */
        const weakTail = WEAK.test(cur[cur.length - 1].w) && !/[.!?…,;:]["”’)]*$/.test(cur[cur.length - 1].w);
        if (cur.length === 1 && weakTail) { /* keep it: it opens the next phrase */ }
        else if (cur.length > 1 && weakTail) { const tail = cur.pop(); flush(); cur.push(tail); }
        else flush();
      }
      else if (cur.length >= limit) {
        /* never strand "the" / "a" / "of" at the end of a group: it opens the next one */
        const tail = cur.length > 1 && WEAK.test(cur[cur.length - 1].w) ? cur.pop() : null;
        flush();
        if (tail) cur.push(tail);
      }
      cur.push(w);
      if (/[.!?…]["”’)]*$/.test(w.w)) flush();
    }
    flush();
    return g.map((ws, k) => {
      const last = ws[ws.length - 1].t1, next = k + 1 < g.length ? g[k + 1][0].t0 : Infinity;
      return { ws, start: ws[0].t0, last, end: Math.max(last, Math.min(next, last + hold)) };
    });
  };

  /* The local time a word is spoken in this scene (c.words), or null. */
  const norm = (s) => String(s).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
  L.wordTime = (c, text) => {
    const key = norm(String(text).replace(/[*~]/g, "").split(/\s+/).filter(Boolean)[0] || "");
    if (!key) return null;
    const hit = (c.words || []).find((w) => norm(w.w) === key);
    return hit ? hit.lt : null;
  };

  /* Label placement at build time. Grid search for the free rect nearest the
     wanted spot inside bounds. o: {w, h, want:{x,y}, bounds:{x0,y0,x1,y1},
     hit(x,y) -> bool (object mask), rects:[{x,y,w,h}] (other labels, title),
     gap(rect) -> px from the rect to the object it points at (optional),
     minGap, maxGap, step, pad}. Returns {x, y, free, moved}. Pure and deterministic. */
  L.placeLabel = (o) => {
    const { w, h, want, bounds: b } = o, step = o.step || 12, pad = o.pad != null ? o.pad : 10, rects = o.rects || [];
    const min = o.minGap != null ? o.minGap : 90, max = o.maxGap != null ? o.maxGap : 260;
    const dots = [];
    for (let v = -pad; v <= h + pad + 1e-6; v += Math.max(8, (h + 2 * pad) / 6)) for (let u = -pad; u <= w + pad + 1e-6; u += Math.max(8, (w + 2 * pad) / 10)) dots.push([u, v]);
    const blocked = (x, y) => {
      for (const r of rects) if (x - pad < r.x + r.w && x + w + pad > r.x && y - pad < r.y + r.h && y + h + pad > r.y) return true;
      if (o.hit) for (const [u, v] of dots) if (o.hit(x + u, y + v)) return true;
      return false;
    };
    const x0 = b.x0, x1 = Math.max(b.x0, b.x1 - w), y0 = b.y0, y1 = Math.max(b.y0, b.y1 - h);
    const wx = clamp(want.x, x0, x1), wy = clamp(want.y, y0, y1);
    const good = (x, y) => { if (blocked(x, y)) return false; if (!o.gap) return true; const g = o.gap({ x, y, w, h }); return g >= min && g <= max; };
    if (good(wx, wy)) return { x: wx, y: wy, free: true, moved: false };
    let best = null, bestCost = Infinity;
    for (let y = y0; y <= y1 + 1e-6; y += step) for (let x = x0; x <= x1 + 1e-6; x += step) {
      let cost = Math.hypot(x - wx, y - wy);
      if (cost >= bestCost) continue;
      if (o.gap) { const g = o.gap({ x, y, w, h }); cost += g < min ? (min - g) * 8 : g > max ? (g - max) * 2 : 0; }
      if (cost >= bestCost || blocked(x, y)) continue;
      best = { x, y }; bestCost = cost;
    }
    return best ? { ...best, free: true, moved: true } : { x: wx, y: wy, free: false, moved: false };
  };
  L.rng = (seed) => { let s = seed >>> 0 || 1; return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296); };
  L.hash = (str) => { let h = 2166136261; for (const ch of String(str)) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; };

  /* ---------------- DOM ---------------- */
  L.el = (tag, cls, parent, html) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    if (parent) parent.appendChild(e);
    return e;
  };
  const SVGNS = "http://www.w3.org/2000/svg";
  L.svg = (tag, attrs, parent) => {
    const e = document.createElementNS(SVGNS, tag);
    if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };
  L.css = (e, o) => { for (const k in o) e.style[k] = o[k]; return e; };
  L.pos = (e, x, y, w, h) => { e.style.left = x + "px"; e.style.top = y + "px"; if (w != null) e.style.width = w + "px"; if (h != null) e.style.height = h + "px"; return e; };
  L.show = (e, o, tf) => { e.style.opacity = o; if (tf != null) e.style.transform = tf; e.style.visibility = o <= 0.001 ? "hidden" : "visible"; };
  const esc = (L.esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));
  /* light inline markup for on-screen text: *accent*, ~serif italic~, **bold**, \n line break */
  L.md = (s) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/\*(.+?)\*/g, '<span class="acc">$1</span>')
    .replace(/~(.+?)~/g, '<span class="serif-it">$1</span>')
    .replace(/\n/g, "<br>");

  /* Entrance helpers. kind: rise | pop | fade | left | blur */
  L.enter = (e, t, t0, d = 0.5, kind = "rise", dist = 26) => {
    const p = kind === "pop" ? L.back(L.seg(t, t0, t0 + d), 1.6) : L.expo(L.seg(t, t0, t0 + d));
    const o = clamp(kind === "pop" ? p * 2 : p * 1.4);
    let tf = "";
    if (kind === "rise") tf = `translateY(${(1 - p) * dist}px)`;
    else if (kind === "left") tf = `translateX(${(1 - p) * dist * 1.4}px)`;
    else if (kind === "pop") tf = `scale(${0.6 + 0.4 * p})`;
    if (kind === "blur") e.style.filter = p < 1 ? `blur(${(1 - p) * 10}px)` : "";
    L.show(e, o, tf);
    return p;
  };

  /* ---------------- pending image decodes ---------------- */
  L.pending = [];
  const urlOf = new WeakMap();
  L.setImg = (img, url) => {
    if (urlOf.get(img) === url) return;
    urlOf.set(img, url);
    img.src = url;
    L.pending.push(img.decode().catch(() => {}));
  };

  /* ---------------- kinetic type ----------------
     Words rise out of a mask, staggered. "~word" is italic serif, "*word*"
     is accent-coloured, "\n" breaks the line. */
  L.words = (parent, text, cls, opts = {}) => {
    const node = L.el("div", "kt " + (cls || ""), parent);
    const spans = [];
    String(text).split("\n").forEach((line, li) => {
      if (li) node.appendChild(document.createElement("br"));
      /* "~a whole line~" or "~a few words~" are serif italic */
      let inIt = false, inAcc = false;
      line.split(/\s+/).filter(Boolean).forEach((w, k) => {
        if (k) node.appendChild(document.createTextNode(" "));
        let c = "kt-w";
        const opens = w.startsWith("~"), closes = /~[.,!?:;…]*$/.test(w);
        if (opens) inIt = true;
        if (inIt) c += " serif-it";
        if (closes) inIt = false;
        w = w.replace(/~/g, "");
        /* *one word* or *a few words* */
        const aOpen = w.startsWith("*"), aClose = /\*[.,!?:;]*$/.test(w);
        if (aOpen) inAcc = true;
        let html = L.esc(w.replace(/\*/g, ""));
        if (inAcc) html = `<span class="acc">${html}</span>`;
        if (aClose) inAcc = false;
        const m = L.el("span", "kt-m", node);
        spans.push(L.el("span", c, m, html));
      });
    });
    const stagger = opts.stagger != null ? opts.stagger : 0.08;
    const dur = opts.dur || 0.55;
    return {
      node, spans,
      at(t, t0) {
        spans.forEach((s, k) => {
          const p = L.expo(L.seg(t, t0 + k * stagger, t0 + k * stagger + dur));
          s.style.transform = `translateY(${(1 - p) * 105}%)`;
          s.style.opacity = p > 0 ? 1 : 0;
        });
      },
      outAt(t, t1, d = 0.35) {
        const p = L.ei(L.seg(t, t1, t1 + d));
        if (p > 0) spans.forEach((s) => { s.style.transform = `translateY(${-p * 105}%)`; });
      },
    };
  };

  L.letters = (parent, text, cls) => {
    const node = L.el("div", "kl " + (cls || ""), parent);
    const spans = [...String(text)].map((ch) => L.el("span", "kl-c", node, ch === " " ? "&nbsp;" : L.esc(ch)));
    return {
      node, spans,
      at(t, t0, stagger = 0.045, dur = 0.5) {
        spans.forEach((s, k) => {
          const p = L.seg(t, t0 + k * stagger, t0 + k * stagger + dur);
          s.style.transform = `translateY(${(1 - L.back(p, 2.2)) * 60}%) scale(${0.6 + 0.4 * L.eo(p)})`;
          s.style.opacity = L.eo(p * 2);
        });
      },
    };
  };

  L.typeAt = (node, text, t, t0, cps = 18, caret = true) => {
    const n = Math.max(0, Math.min(text.length, Math.floor((t - t0) * cps)));
    const on = caret && (t < t0 || n < text.length || Math.floor(t * 2.2) % 2 === 0);
    node.innerHTML = L.esc(text.slice(0, n)) + (caret ? `<i class="caret" style="opacity:${on ? 1 : 0}"></i>` : "");
    return n;
  };

  /* fit a text node's font-size so it fits w×h (binary search, deterministic) */
  L.fit = (node, maxPx, minPx, w, h) => {
    let lo = minPx, hi = maxPx;
    node.style.fontSize = hi + "px";
    if (node.scrollWidth <= w + 1 && node.scrollHeight <= h + 1) return hi;
    for (let i = 0; i < 12; i++) {
      const mid = (lo + hi) / 2;
      node.style.fontSize = mid + "px";
      if (node.scrollWidth <= w + 1 && node.scrollHeight <= h + 1) lo = mid; else hi = mid;
    }
    node.style.fontSize = Math.floor(lo) + "px";
    return Math.floor(lo);
  };

  /* hero type: the largest size at which the text fills width w in at most `lines`
     lines. Hard breaks stay; words never overflow. Returns the px size. */
  L.fitHero = (node, o = {}) => {
    /* lines is a number; anything else (a list, a string) falls back to the default */
    const w = o.w, lines = +o.lines > 0 ? +o.lines : 2, max = o.max || 200, min = o.min || 40;
    node.style.width = w + "px"; node.style.maxWidth = w + "px";
    node.style.textWrap = "balance";
    const count = () => {
      const sp = [...node.querySelectorAll(".fv-sw, .fv-sub")];
      if (sp.length) return new Set(sp.map((s) => s.offsetTop)).size;
      const lh = parseFloat(getComputedStyle(node).lineHeight) || parseFloat(node.style.fontSize);
      return Math.round(node.offsetHeight / lh);
    };
    const ok = (px) => { node.style.fontSize = px + "px"; return node.scrollWidth <= w + 1 && count() <= lines; };
    if (ok(max)) return max;
    let lo = min, hi = max;
    for (let i = 0; i < 10; i++) { const mid = (lo + hi) / 2; if (ok(mid)) lo = mid; else hi = mid; }
    const px = Math.floor(lo);
    node.style.fontSize = px + "px";
    return px;
  };

  /* ---------------- hand-drawn strokes (rough.js) ----------------
     Each drawable becomes SVG paths with pathLength=1, drawn on by dash
     offset. draw(p) returns the pen-tip point while drawing. */
  let gen = null;
  L.rough = (svgParent, kind, args, opts = {}) => {
    if (!gen) gen = rough.generator();
    const o = Object.assign({ roughness: 1.1, bowing: 1.2, stroke: L.C.ink, strokeWidth: 2.8, seed: 7 }, opts);
    const d = gen[kind](...args, o);
    const g = L.svg("g", { class: "rough" }, svgParent);
    const paths = [], fills = [];
    for (const p of gen.toPaths(d)) {
      const isFill = !!(o.fill && o.fill !== o.stroke && p.stroke === o.fill);
      const e = L.svg("path", { d: p.d, fill: p.fill || "none", stroke: p.stroke, "stroke-width": p.strokeWidth, "stroke-linecap": "round", "stroke-linejoin": "round" }, g);
      if (p.fill && p.fill !== "none") { e.setAttribute("opacity", 0); fills.push(e); continue; }
      e.setAttribute("pathLength", 1);
      e.setAttribute("stroke-dasharray", "1 1");
      e.setAttribute("stroke-dashoffset", 1);
      (isFill ? fills : paths).push(e);
    }
    const lens = paths.map((p) => { try { return p.getTotalLength(); } catch (e) { return 1; } });
    const total = lens.reduce((a, b) => a + b, 0) || 1;
    return {
      g, paths, fills,
      draw(p, fillP) {
        p = clamp(p);
        let acc = 0, tip = null;
        const target = p * total;
        paths.forEach((e, i) => {
          const a = clamp((target - acc) / lens[i]);
          e.setAttribute("stroke-dashoffset", 1 - a);
          if (a > 0 && a < 1) { try { tip = e.getPointAtLength(a * lens[i]); } catch (x) {} }
          acc += lens[i];
        });
        const fp = fillP == null ? clamp(p * 1.4 - 0.4) : fillP;
        fills.forEach((e) => { if (e.hasAttribute("pathLength")) e.setAttribute("stroke-dashoffset", 1 - fp); else e.setAttribute("opacity", fp); });
        return tip;
      },
    };
  };

  /* a marker pen that follows the stroke tip */
  L.pen = (parent) => {
    const g = L.svg("g", { class: "pen" }, parent);
    L.svg("path", { d: "M0 0 L10 -6 L58 -54 Q64 -60 70 -54 L74 -50 Q80 -44 74 -38 L26 10 L20 14 Z", fill: L.C.ink, opacity: 0.92 }, g);
    L.svg("path", { d: "M0 0 L10 -6 L20 4 L14 10 Z", fill: L.C.accent }, g);
    return {
      g,
      at(pt, vis) {
        if (!pt || vis <= 0) { g.setAttribute("opacity", 0); return; }
        g.setAttribute("opacity", vis);
        g.setAttribute("transform", `translate(${pt.x.toFixed(1)} ${pt.y.toFixed(1)})`);
      },
    };
  };

  /* ---------------- logo ----------------
     The brand logo (an image from the project) or a typographic badge made
     from the brand name. Returns {node, at(t, t0)}. */
  L.logo = (parent, brand, size) => {
    const node = L.el("div", "abs logo", parent);
    node.style.width = node.style.height = size + "px";
    if (brand && brand.logo) {
      const img = L.el("img", "", node);
      img.style.cssText = "width:100%;height:100%;object-fit:contain";
      L.setImg(img, "/project/" + brand.logo.replace(/^\/+/, ""));
    } else {
      const name = (brand && brand.name) || "•";
      const ini = name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
      node.innerHTML = `<div style="width:100%;height:100%;border-radius:28%;background:var(--ink);display:grid;place-items:center;color:var(--bg);font-weight:800;font-size:${size * 0.42}px;letter-spacing:-.04em;box-shadow:0 20px 40px -20px rgba(0,0,0,.5)">${L.esc(ini)}<i style="position:absolute;right:${size * 0.12}px;bottom:${size * 0.12}px;width:${size * 0.14}px;height:${size * 0.14}px;border-radius:50%;background:var(--accent)"></i></div>`;
      node.firstChild.style.position = "relative";
    }
    return {
      node,
      at(t, t0) {
        const p = L.back(L.seg(t, t0, t0 + 0.8), 1.6);
        node.style.opacity = clamp(p * 2);
        node.style.transform = `scale(${0.5 + 0.5 * p}) rotate(${(1 - L.eo(L.seg(t, t0, t0 + 1))) * -25}deg)`;
      },
    };
  };

  /* ---------------- captures: meta + browser window with camera ---------------- */
  L.META = {};
  L.loadMeta = async (shots) => {
    await Promise.all(shots.map(async (s) => {
      const r = await fetch(`/project/build/cap/${s}/meta.json`);
      if (!r.ok) throw new Error(`capture "${s}" is missing: run \`fishvideo capture\` first`);
      L.META[s] = await r.json();
    }));
  };
  L.frameUrl = (shot, f) => `/project/build/cap/${shot}/${String(f).padStart(5, "0")}.jpg`;
  L.mark$ = (shot, name) => { const m = L.META[shot]; return m && m.marks[name] != null ? m.marks[name] : 0; };
  L.focusAt = (shot, f, win = 14) => {
    const fr = L.META[shot].frames;
    let sx = 0, sy = 0, sw = 0;
    for (let k = -win; k <= win; k++) {
      const q = fr[clamp(f + k, 0, fr.length - 1)];
      const w = 1 - Math.abs(k) / (win + 1);
      sx += q.x * w; sy += q.y * w; sw += w;
    }
    return { x: sx / sw, y: sy / sw };
  };
  /* camera keyframes over capture frames: [{f, z, x, y}]; x/y omitted = follow the smoothed cursor */
  L.cam = (shot, keys, f) => {
    const at = (k) => { const fc = L.focusAt(shot, Math.round(f)); return { z: k.z || 1, x: k.x != null ? k.x : fc.x, y: k.y != null ? k.y : fc.y }; };
    if (f <= keys[0].f) return at(keys[0]);
    for (let i = 0; i < keys.length - 1; i++) {
      const a = keys[i], b = keys[i + 1];
      if (f <= b.f) {
        const p = L.eio(L.seg(f, a.f, b.f));
        const A = at(a), B = at(b);
        return { z: L.lerp(A.z, B.z, p), x: L.lerp(A.x, B.x, p), y: L.lerp(A.y, B.y, p) };
      }
    }
    return at(keys[keys.length - 1]);
  };

  const CURSOR = '<svg viewBox="0 0 28 28" width="28" height="28"><path d="M5 3 L5 22 L10 17.5 L13.6 25 L17 23.4 L13.5 16 L20 16 Z" fill="#1a1714" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/></svg>';

  const GLOWCUR = '<svg viewBox="0 0 28 28" width="28" height="28" style="position:relative"><path d="M5 3 L5 22 L10 17.5 L13.6 25 L17 23.4 L13.5 16 L20 16 Z" fill="#ffffff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';

  /* Automatic zoom-to-cursor: clicks close in time (and scroll position) form
     a cluster; the camera eases in to z (1.6-2x) before the first click,
     follows the smoothed cursor, and pulls back after the last click or on a
     context change (a scroll jump or a gap). o: {z, ease (s), hold (s), gap (s)} */
  L.autoCam = (shot, f, o = {}) => {
    const m = L.META[shot];
    const fps = m.fps || 30, Z = o.z || 1.8, ease = (o.ease || 0.5) * fps, hold = (o.hold != null ? o.hold : 1.0) * fps, gap = (o.gap || 2.5) * fps;
    const key = `${gap}`;
    m._clusters = m._clusters || {};
    if (!m._clusters[key]) {
      const cl = [];
      m.frames.forEach((q, i) => {
        if (!q.c) return;
        const last = cl[cl.length - 1];
        if (last && i - last.b <= gap && Math.abs((q.s || 0) - last.s) < 240) last.b = i;
        else cl.push({ a: i, b: i, s: q.s || 0 });
      });
      m._clusters[key] = cl;
    }
    let z = 1;
    for (const c of m._clusters[key]) {
      const zin = L.eio(L.seg(f, c.a - ease - 6, c.a - 6));
      const zout = 1 - L.eio(L.seg(f, c.b + hold, c.b + hold + ease));
      z = Math.max(z, 1 + (Z - 1) * Math.min(zin, zout));
    }
    const fc = L.focusAt(shot, Math.round(clamp(f, 0, m.count - 1)), 10);
    return { z, x: fc.x, y: fc.y };
  };
  /* the frames where autoCam starts moving (for swish cues) */
  L.autoCamMoves = (shot, o = {}) => {
    const m = L.META[shot];
    if (!m) return [];
    L.autoCam(shot, 0, o);
    const fps = m.fps || 30, ease = (o.ease || 0.5) * fps, hold = (o.hold != null ? o.hold : 1.0) * fps;
    return m._clusters[`${(o.gap || 2.5) * fps}`].flatMap((c) => [c.a - ease - 6, c.b + hold]);
  };

  /* A browser window that plays a captured shot. win.at(f, cam) with cam = {z, x, y} in page CSS px. */
  L.Win = function (parent, o = {}) {
    const shot = o.shot;
    const meta = L.META[shot];
    const CW = meta.w, CH = meta.h;
    const node = L.el("div", "win" + (o.bare ? " bare" : ""), parent);
    const bar = o.bare ? null : L.el("div", "win-bar", node, `<i></i><i></i><i></i><span class="win-url">${L.esc(o.url || "")}</span>`);
    const view = L.el("div", "win-view", node);
    const img = L.el("img", "win-img", view);
    img.style.width = CW + "px"; img.style.height = CH + "px";
    const fx = L.el("div", "win-fx", view);
    /* cursor: true (plain) | "glow" (white arrow, ~1.5x, soft halo) | false */
    const glow = o.cursor === "glow";
    const cur = glow ? L.el("div", "glowcur", view, '<i class="halo"></i>' + GLOWCUR) : L.el("div", "cursor", view, CURSOR);
    const keys = L.el("div", "keys", node);
    const BARH = o.bare ? 0 : 44;
    /* cover: the view fills its box (a portrait crop of a landscape capture) and the camera pans to the focus */
    const cover = !!o.cover;
    const self = {
      node, view, img, shot, meta, BARH,
      layout(x, y, w, maxH) {
        let h = Math.round((w * CH) / CW);
        if (cover && maxH) h = maxH - BARH;
        else if (maxH && h + BARH > maxH) { h = maxH - BARH; w = Math.round((h * CW) / CH); }
        L.pos(node, x, y, w, h + BARH);
        L.pos(view, 0, BARH, w, h);
        self.VW = w; self.VH = h; self.X = x; self.Y = y;
        return { w, h: h + BARH };
      },
      at(f, cam, opts = {}) {
        f = Math.round(clamp(f, 0, meta.count - 1));
        L.setImg(img, L.frameUrl(shot, f));
        const s0 = cover ? Math.max(self.VW / CW, self.VH / CH) : self.VW / CW;
        const z = cam ? cam.z : 1;
        const S = s0 * z;
        let tx = 0, ty = 0;
        if (cam && (z > 1.0001 || cover)) {
          tx = clamp(self.VW / 2 - cam.x * S, self.VW - CW * S, 0);
          ty = clamp(self.VH / 2 - cam.y * S, self.VH - CH * S, 0);
        }
        img.style.transform = `translate(${tx.toFixed(2)}px, ${ty.toFixed(2)}px) scale(${S.toFixed(5)})`;
        const fr = meta.frames[f];
        if (opts.cursor !== false && fr) {
          const cs = clamp(0.9 + (z - 1) * 0.5, 0.9, 1.5) * (glow ? 1.5 : 1);
          cur.style.display = "block";
          cur.style.transform = `translate(${(fr.x * S + tx - 5 * cs).toFixed(1)}px, ${(fr.y * S + ty - 3 * cs).toFixed(1)}px) scale(${(cs * (fr.d ? 0.86 : 1)).toFixed(3)})`;
        } else cur.style.display = "none";
        let html = "";
        for (let k = 0; k <= 21; k++) {
          const q = meta.frames[f - k];
          if (!q || !q.c) continue;
          const p = k / 21, px = q.x * S + tx, py = q.y * S + ty, r = 10 + L.eo(p) * 46;
          html += `<i class="ripple${glow ? " glow" : ""}" style="left:${px.toFixed(1)}px;top:${py.toFixed(1)}px;width:${r * 2}px;height:${r * 2}px;margin:-${r}px 0 0 -${r}px;opacity:${(1 - p) * 0.9}"></i>`;
          html += `<i class="ripple dot" style="left:${px.toFixed(1)}px;top:${py.toFixed(1)}px;opacity:${(1 - L.eo(p * 1.6)) * 0.6}"></i>`;
        }
        fx.innerHTML = html;
        let kh = "";
        for (let k = 0; k <= 36; k++) {
          const q = meta.frames[f - k];
          if (!q || !q.k || q.k.indexOf("+") < 0) continue;
          const a = Math.min(L.eo(k / 4), 1 - L.ei(L.seg(k / 36, 0.7, 1)));
          const caps = q.k.split("+").map((c) => (c === "Control" ? "Ctrl" : c === "Meta" ? "⌘" : c.toUpperCase())).map((c) => `<kbd>${L.esc(c)}</kbd>`).join("<em>+</em>");
          kh = `<div class="keycombo" style="opacity:${a};transform:translate(-50%, ${(1 - L.eo(k / 6)) * 18}px)">${caps}</div>`;
          break;
        }
        keys.innerHTML = kh;
        return { S, tx, ty };
      },
      map(pt, r) { return { x: pt.x * r.S + r.tx, y: pt.y * r.S + r.ty + BARH }; },
    };
    return self;
  };

  /* clicks / keys inside a capture window, as sound cues */
  L.capCues = (shot, f0, speed, lt0, lt1) => {
    const m = L.META[shot];
    const out = [];
    if (!m) return out;
    for (let f = 0; f < m.count; f++) {
      const q = m.frames[f];
      if (!q.c && !q.k) continue;
      const lt = (f - f0) / (L.FPS * speed);
      if (lt < lt0 || lt > lt1) continue;
      if (q.c) out.push({ lt, type: "click", lvl: 2 });
      if (q.k) out.push({ lt, type: q.k.indexOf("+") >= 0 ? "keycombo" : "key", lvl: 1 });
    }
    /* runs of single keys become one typing {len} cue */
    const merged = [];
    for (const q of out) {
      const prev = merged[merged.length - 1];
      if (q.type === "key" && prev && (prev.type === "typing" || prev.type === "key") && q.lt - (prev.lt + (prev.len || 0)) < 0.45) { prev.type = "typing"; prev.len = +(q.lt - prev.lt + 0.08).toFixed(3); prev.lvl = 2; continue; }
      merged.push(q.type === "key" ? { ...q, type: "typing", len: 0.1 } : q);
    }
    return merged;
  };

  /* ---------------- grain ---------------- */
  L.grainTiles = (() => {
    let tiles = null;
    return () => {
      if (tiles) return tiles;
      tiles = [];
      for (let n = 0; n < 6; n++) {
        const c = document.createElement("canvas");
        c.width = c.height = 220;
        const x = c.getContext("2d");
        const d = x.createImageData(220, 220);
        const r = L.rng(91 + n * 17);
        for (let i = 0; i < d.data.length; i += 4) { const v = r() * 255; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; }
        x.putImageData(d, 0, 0);
        tiles.push(c.toDataURL("image/png"));
      }
      return tiles;
    };
  })();
})();
