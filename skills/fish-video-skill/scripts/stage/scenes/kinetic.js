/* kstack: the kinetic-explainer scene. The narration IS the visual: the spoken words enter one to three at a time
   (rise + fade + blur-in, light grey darkening to the ink in ~0.25 s), stacked in 2 to 4 centred lines with mixed
   size and weight, in the upper part of the frame; one element sits below the type.
   The grammar is measured from kinetic-typography explainer Shorts; no text, colour, asset or brand is baked in:
   colours and type come from the theme (L.C, --display / --serif), content from params.

   params
     lines   [string]  the stack, 2 to 4 lines. Markup per word group:
                 plain       glue word: small, light
                 **word**    key word: huge, bold   (**two words** works)
                 ==word==    key word in the accent colour (use for ONE word at most)
                 *word*      emphasis: serif italic, mid size
             A line with no key word is a calm lead-in line ("Third is", "It's called").
     number  string    a list label ("First", "Second") as the first, huge, accent-coloured line (number_color: ink)
     element card | pill | orbit | hero | none   (default: whichever of card/pill/orbit/hero is given, else none)
       card   {src, ar (1.5), chrome (browser dots), drift (zoom|none), word|at}      rounded shadow card holding a real picture
       pill   {name, logo {slug|src|d|glyph}, word|at}                                 icon tile + UPPERCASE name
       orbit  {center {slug|src|d|glyph}, items [{slug|src|d|glyph}] (5 to 8), rings (2), word|at}   logos orbiting on faint rings
       hero   {src, kind: "cutout", shape (burst|circle), side (left|center|right), word|at}  grey cut-out over a big accent shape
     handle  string    a small faint handle in the lower third (only what the brief gives; never invented)
     boom    true | {word|at}   a low boom on the element's entrance (the reveal)
     blur_in / blur_out  seconds of heavy-blur between sections (default 0.1 = 3 frames at 30 fps; 0 = off; the first scene never blurs in)
   A logo item is {slug} (a simple-icons slug, resolved to a path at build time by `fishvideo storyboard`), {d, hex, tile},
   {src} (a picture under the project) or {glyph} (a letter or symbol).
   Words land on the spoken word they match (in order); the rest are interpolated. Pure functions of time. */
(function () {
  "use strict";
  const S = (window.SCENES = window.SCENES || {});
  const { el, seg, clamp, C } = L;

  const norm = (s) => String(s).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
  const SIZE = { key: 1, acc: 1, num: 1.25, it: 0.7, glue: 0.4 };       /* sizes relative to the line's key size */
  const SIZE_NOKEY = { key: 1, acc: 1, num: 1.25, it: 1.25, glue: 1 };  /* a lead-in line has no key: its own scale */

  /* ---------------- pure helpers (also used by tests) ---------------- */
  function parseLine(raw) {
    const toks = [];
    let mode = null;
    String(raw).split(/\s+/).filter(Boolean).forEach((w0) => {
      let w = w0;
      if (!mode) {
        if (w.startsWith("**")) { mode = "key"; w = w.slice(2); }
        else if (w.startsWith("==")) { mode = "acc"; w = w.slice(2); }
        else if (w.startsWith("*")) { mode = "it"; w = w.slice(1); }
      }
      const kind = mode || "glue";
      const closes = (mode === "key" && /\*\*[^\p{L}\p{N}]*$/u.test(w)) || (mode === "acc" && /==[^\p{L}\p{N}]*$/u.test(w)) || (mode === "it" && /\*[^\p{L}\p{N}*]*$/u.test(w));
      if (closes) w = w.replace(/(\*\*|==|\*)(?=[^\p{L}\p{N}]*$)/u, "");
      if (closes) mode = null;
      if (w) toks.push({ text: w, kind });
    });
    return toks;
  }
  function parse(p) {
    const lines = (Array.isArray(p.lines) ? p.lines : String(p.lines || "").split("\n")).map(parseLine).filter((l) => l.length);
    if (p.number) lines.unshift([{ text: String(p.number), kind: "num" }]);
    return lines;
  }
  /* the time (scene-local, s) each token lands: the matching spoken word, in order; the rest interpolated */
  function schedule(lines, words, dur) {
    const toks = lines.flat(), n = toks.length, ws = words || [];
    const t = new Array(n).fill(null);
    let ptr = 0;
    toks.forEach((tk, i) => {
      const key = norm(tk.text);
      if (!key) return;
      for (let j = ptr; j < Math.min(ws.length, ptr + 7); j++) if (norm(ws[j].w) === key) { t[i] = ws[j].lt; ptr = j + 1; break; }
    });
    if (!ws.length) return toks.map((_, i) => 0.12 + (n > 1 ? (i * Math.max(0.5, dur * 0.7 - 0.12)) / (n - 1) : 0));
    for (let i = 0; i < n; i++) {
      if (t[i] != null) continue;
      let a = i - 1; while (a >= 0 && t[a] == null) a--;
      let b = i + 1; while (b < n && t[b] == null) b++;
      const ta = a >= 0 ? t[a] : null, tb = b < n ? t[b] : null;
      t[i] = ta != null && tb != null ? ta + ((tb - ta) * (i - a)) / (b - a) : ta != null ? ta + 0.2 * (i - a) : tb != null ? Math.max(0, tb - 0.2 * (b - i)) : 0.12;
    }
    for (let i = 1; i < n; i++) t[i] = Math.max(t[i], t[i - 1]);
    return t.map((v) => Math.max(0, Math.min(v, dur - 0.1)));
  }
  /* tokens that land within 0.16 s of each other are one group: one tick of sound */
  function groups(times) {
    const g = [];
    times.forEach((tt, i) => { if (!g.length || tt - g[g.length - 1].t > 0.16) g.push({ t: tt, first: i }); });
    return g;
  }
  /* the scene clock without the entrance lead (main.js warps it so scenes open with their subject up) */
  function realT(t, c) {
    const lead = c.lead || 0;
    if (!lead || t >= 1.2 + lead) return t;
    let lo = 0, hi = 1.2;
    for (let k = 0; k < 24; k++) { const m = (lo + hi) / 2, f = m + lead * (1 - seg(m, 0, 1.2)); if (f < t) lo = m; else hi = m; }
    return (lo + hi) / 2;
  }
  window.KSTACK = { parseLine, parse, schedule, groups, realT };

  /* ---------------- layout zones ---------------- */
  function zones(c, hasEl) {
    const s = c.safe;
    if (!c.P) {
      return hasEl
        ? { text: { x: s.x, y: s.y, w: s.w * 0.5, h: s.h, mid: true }, el: { x: s.x + s.w * 0.53, y: s.y + s.h * 0.04, w: s.w * 0.47, h: s.h * 0.92 } }
        : { text: { x: s.x, y: s.y, w: s.w, h: s.h, mid: true }, el: null };
    }
    return hasEl
      ? { text: { x: s.x, y: s.y + s.h * 0.015, w: s.w, h: s.h * 0.39 }, el: { x: s.x, y: s.y + s.h * 0.43, w: s.w, h: s.h * 0.53 } }
      : { text: { x: s.x, y: s.y + s.h * 0.06, w: s.w, h: s.h * 0.62 }, el: null };
  }

  const grey = () => L.mix(C.bg, C.ink, 0.28);
  const finalColor = (kind, numInk) => (kind === "acc" ? C.accent : kind === "num" ? (numInk ? C.ink : C.accent) : kind === "glue" ? L.mix(C.ink, C.bg, 0.14) : C.ink);

  /* ---------------- element helpers ---------------- */
  const SHADOW = (u) => `0 ${34 * u}px ${70 * u}px -${24 * u}px rgba(15,15,20,.42), 0 ${10 * u}px ${24 * u}px -${6 * u}px rgba(15,15,20,.16)`;
  function tile(parent, item, size, u) {
    const it = item || {};
    const n = el("div", "", parent);
    n.style.cssText = `position:relative;width:${size}px;height:${size}px;border-radius:${size * 0.26}px;background:${it.tile || "#ffffff"};display:grid;place-items:center;overflow:hidden;box-shadow:0 ${size * 0.1}px ${size * 0.22}px -${size * 0.08}px rgba(15,15,20,.35)`;
    if (it.d) {
      n.innerHTML = `<svg viewBox="0 0 24 24" width="${size * 0.58}" height="${size * 0.58}"><path d="${it.d}" fill="${it.hex ? "#" + String(it.hex).replace("#", "") : C.ink}"/></svg>`;
    } else if (it.src) {
      const im = el("img", "", n);
      im.style.cssText = "width:100%;height:100%;object-fit:contain";
      L.setImg(im, L.projUrl(it.src));
    } else if (it.glyph || it.text) {
      n.innerHTML = `<span style="font:800 ${size * 0.5}px/1 var(--display);color:${C.ink}">${L.esc(String(it.glyph || it.text).slice(0, 2))}</span>`;
    } else {
      n.innerHTML = `<i style="width:${size * 0.3}px;height:${size * 0.3}px;border-radius:50%;background:${C.accent}"></i>`;
    }
    return n;
  }
  const pop = (t, t0, d = 0.5) => L.back(seg(t, t0, t0 + d), 1.5);
  const slide = (t, t0, d = 0.55) => L.expo(seg(t, t0, t0 + d));

  function buildCard(parent, c, z, o) {
    const u = c.u, ar = o.ar || 1.5;
    let w = Math.min(z.w * 0.9, z.h * 0.96 * ar), h = w / ar;
    if (h > z.h * 0.96) { h = z.h * 0.96; w = h * ar; }
    const x = z.x + (z.w - w) / 2, y = z.y + (z.h - h) / 2;
    const box = el("div", "", parent);
    box.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;border-radius:${30 * u}px;background:#fff;box-shadow:${SHADOW(u)};overflow:hidden`;
    const inner = el("div", "", box);
    inner.style.cssText = "position:absolute;inset:0;overflow:hidden";
    const img = el("img", "", inner);
    img.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;transform-origin:50% 40%";
    if (o.src) L.setImg(img, L.projUrl(o.src));
    else {
      img.remove();
      inner.style.background = L.mix("#ffffff", C.ink, 0.04);
      inner.innerHTML = `<div style="position:absolute;left:8%;top:12%;width:44%;height:${14 * u}px;border-radius:99px;background:${L.hexA(C.ink, 0.14)}"></div>` +
        [0, 1, 2, 3].map((i) => `<div style="position:absolute;left:8%;top:${28 + i * 15}%;width:${[84, 70, 78, 52][i]}%;height:${10 * u}px;border-radius:99px;background:${L.hexA(C.ink, 0.07)}"></div>`).join("");
    }
    let bar = null;
    if (o.chrome) {
      bar = el("div", "", box);
      bar.style.cssText = `position:absolute;left:0;top:0;right:0;height:${44 * u}px;background:rgba(255,255,255,.92);display:flex;align-items:center;gap:${9 * u}px;padding-left:${18 * u}px`;
      bar.innerHTML = ["#ff5f57", "#febc2e", "#28c840"].map((k) => `<i style="width:${13 * u}px;height:${13 * u}px;border-radius:50%;background:${k}"></i>`).join("");
    }
    return {
      node: box,
      at(t, t0, dur) {
        const e = slide(t, t0, 0.55), pp = pop(t, t0, 0.55), life = clamp((t - t0) / Math.max(1, dur - t0));
        const sy = Math.sin(t * 0.9) * 5 * u, rot = Math.sin(t * 0.55 + 1) * 0.45;
        L.show(box, clamp(e * 1.6), `translateY(${((1 - e) * 120 * u + sy).toFixed(2)}px) scale(${(0.9 + 0.1 * pp).toFixed(4)}) rotate(${rot.toFixed(3)}deg)`);
        box.style.filter = e < 1 ? `blur(${((1 - e) * 8).toFixed(2)}px)` : "";
        if (o.drift !== "none" && o.src) img.style.transform = `scale(${(1.02 + 0.075 * life).toFixed(4)}) translate(${((life - 0.5) * -2.2).toFixed(3)}%, ${((0.5 - life) * 1.4).toFixed(3)}%)`;
      },
    };
  }

  function buildPill(parent, c, z, o) {
    const u = c.u, h = 150 * u;
    const box = el("div", "", parent);
    box.style.cssText = `position:absolute;display:flex;align-items:center;gap:${26 * u}px;height:${h}px;padding:0 ${44 * u}px 0 ${20 * u}px;border-radius:${h}px;background:#fff;box-shadow:${SHADOW(u)};white-space:nowrap`;
    tile(box, o.logo || { glyph: String(o.name || "?")[0] }, h * 0.74, u).style.flex = "none";
    const nm = el("span", "", box, L.esc(String(o.name || "").toUpperCase()));
    let px = 84 * u;
    nm.style.cssText = `font:800 ${px}px/1 var(--display);letter-spacing:.035em;color:${C.ink}`;
    const maxW = z.w * 0.94;
    if (box.offsetWidth > maxW) { px = px * (maxW / box.offsetWidth); nm.style.fontSize = px + "px"; }
    const w = box.offsetWidth;
    box.style.left = z.x + (z.w - w) / 2 + "px";
    box.style.top = (o.top != null ? o.top : z.y + z.h * 0.22) + "px";
    return {
      node: box,
      at(t, t0) {
        const pp = pop(t, t0, 0.5), e = slide(t, t0, 0.4);
        L.show(box, clamp(e * 2), `translateY(${((1 - e) * 40 * u + Math.sin(t * 1.1) * 4 * u).toFixed(2)}px) scale(${(0.62 + 0.38 * pp).toFixed(4)})`);
        box.style.filter = e < 1 ? `blur(${((1 - e) * 7).toFixed(2)}px)` : "";
      },
    };
  }

  function buildOrbit(parent, c, z, o) {
    const u = c.u, D = Math.min(z.w * 0.98, z.h * 1.1), cx = z.x + z.w / 2, cy = z.y + z.h / 2;
    const items = (o.items || []).slice(0, 8), rings = Math.max(1, Math.min(3, o.rings || (items.length > 4 ? 2 : 1)));
    const ts = D * 0.17, cs = D * 0.27, R = D / 2 - ts / 2;
    const radii = rings === 1 ? [R] : rings === 2 ? [R * 0.56, R] : [R * 0.4, R * 0.7, R];
    const root = el("div", "", parent);
    root.style.cssText = "position:absolute;left:0;top:0;width:0;height:0";
    const svg = L.svg("svg", { width: c.W, height: c.H, viewBox: `0 0 ${c.W} ${c.H}` }, root);
    svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible";
    const ringEls = radii.map((r, k) => L.svg("circle", { cx, cy, r: 1, fill: "none", stroke: L.hexA(C.ink, k === radii.length - 1 ? 0.16 : 0.1), "stroke-width": 2 * u }, svg));
    const centre = el("div", "", root);
    centre.style.cssText = `position:absolute;left:${cx - cs / 2}px;top:${cy - cs / 2}px`;
    tile(centre, o.center || { glyph: "*" }, cs, u);
    /* items round-robin over the rings, outermost first */
    const per = radii.map(() => []);
    items.forEach((it, i) => per[radii.length - 1 - (i % radii.length)].push(it));
    const nodes = [];
    per.forEach((list, k) => list.forEach((it, j) => {
      const n = el("div", "", root);
      n.style.cssText = `position:absolute;left:${-ts / 2}px;top:${-ts / 2}px`;
      tile(n, it, ts, u);
      nodes.push({ n, k, a0: (2 * Math.PI * j) / list.length + k * 0.9 + 0.4, dir: k % 2 ? -1 : 1, r: radii[k], i: nodes.length });
    }));
    return {
      node: root,
      at(t, t0) {
        const e = slide(t, t0, 0.6), cp = pop(t, t0, 0.5);
        ringEls.forEach((r, k) => { const q = slide(t, t0 + 0.08 * k, 0.6); r.setAttribute("r", (radii[k] * q).toFixed(2)); r.style.opacity = clamp(q * 2).toFixed(3); });
        L.show(centre, clamp(e * 2), `scale(${(0.5 + 0.5 * cp).toFixed(4)})`);
        centre.style.transformOrigin = "50% 50%";
        nodes.forEach((q) => {
          const t1 = t0 + 0.18 + 0.07 * q.i, ep = pop(t, t1, 0.5), sp = slide(t, t0, 1.1);
          const ang = q.a0 + q.dir * (t - t0) * ((2 * Math.PI) / (26 + q.k * 9)) + (1 - sp) * q.dir * 1.4;
          q.n.style.opacity = clamp(ep * 2).toFixed(3);
          q.n.style.visibility = ep <= 0.001 ? "hidden" : "visible";
          q.n.style.transform = `translate(${(cx + Math.cos(ang) * q.r * Math.min(1, sp * 1.2)).toFixed(2)}px, ${(cy + Math.sin(ang) * q.r * Math.min(1, sp * 1.2)).toFixed(2)}px) scale(${(0.4 + 0.6 * ep).toFixed(4)})`;
        });
      },
    };
  }

  function burstSvg(parent, r, accent, n) {
    const svg = L.svg("svg", { width: r * 2, height: r * 2, viewBox: `${-r} ${-r} ${r * 2} ${r * 2}` }, parent);
    svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible";
    for (let i = 0; i < n; i++) {
      const a = (360 / n) * i, w0 = r * 0.27, w1 = r * 0.17, l0 = r * 0.3, l1 = r * (i % 2 ? 0.84 : 1);
      L.svg("polygon", { points: `${l0},${-w0 / 2} ${l1},${-w1 / 2} ${l1 + r * 0.03},0 ${l1},${w1 / 2} ${l0},${w0 / 2}`, fill: accent, transform: `rotate(${a})` }, svg);
    }
    return svg;
  }

  function buildHero(parent, c, z, o) {
    const u = c.u, url = L.projUrl(o.src || ""), info = L.cutInfo(url);
    const side = o.side || "left";
    const asp = info ? (info.h * info.nh) / (info.w * info.nw) : 1.15;
    let w = Math.min(z.w * 0.86, (z.h * 1.02) / asp), h = w * asp;
    const x = side === "center" ? z.x + (z.w - w) / 2 : side === "right" ? z.x + z.w - w : z.x;
    const y = z.y + z.h - h + z.h * 0.02;
    const r = Math.min(z.w, z.h) * 0.66;
    const sh = el("div", "", parent);
    const shx = x + w * (side === "right" ? 0.3 : side === "center" ? 0.62 : 0.66), shy = y + h * 0.4;
    sh.style.cssText = `position:absolute;left:${shx - r}px;top:${shy - r}px;width:${r * 2}px;height:${r * 2}px`;
    if ((o.shape || "burst") === "circle") {
      sh.style.borderRadius = "50%"; sh.style.background = C.accent;
    } else burstSvg(sh, r, C.accent, 9);
    sh.style.filter = `drop-shadow(0 ${18 * u}px ${22 * u}px rgba(15,15,20,.22))`;
    const node = el("div", "", parent);
    node.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;transform-origin:50% 100%`;
    const img = el("img", "", node);
    if (info) { const iw = w / info.w, ih = h / info.h; img.style.cssText = `position:absolute;left:${-info.x * iw}px;top:${-info.y * ih}px;width:${iw}px;height:${ih}px;max-width:none`; }
    else img.style.cssText = "position:absolute;inset:0;width:100%;height:100%;object-fit:contain";
    img.style.filter = `grayscale(1) contrast(1.12) drop-shadow(${10 * u}px ${16 * u}px ${18 * u}px rgba(15,15,20,.38))`;
    if (o.src) L.setImg(img, url);
    return {
      node,
      at(t, t0, dur) {
        const e = slide(t, t0, 0.6), life = clamp((t - t0) / Math.max(1, dur - t0));
        L.show(node, clamp(e * 1.8), `translateY(${((1 - e) * 0.16 * h).toFixed(2)}px) scale(${(1 + 0.05 * life).toFixed(4)})`);
        const q = slide(t, t0 - 0.05, 0.7);
        L.show(sh, clamp(q * 2), `rotate(${((1 - q) * -34 + life * 6).toFixed(2)}deg) scale(${(0.55 + 0.45 * q).toFixed(4)})`);
      },
    };
  }

  /* ================================================================ kstack */
  S.kstack = {
    build(root, c) {
      const p = c.p, u = c.u, st = {};
      const lines = parse(p);
      const elKind = p.element || (p.card ? "card" : p.pill ? "pill" : p.orbit ? "orbit" : p.hero ? "hero" : "none");
      const Z = zones(c, elKind !== "none");
      const wrap = (st.wrap = el("div", "abs", root));
      L.pos(wrap, 0, 0, c.W, c.H);
      wrap.dataset.nolint = "";
      /* the type stack: every word is laid out from frame 0 (hidden), so nothing reflows when it lands */
      const tz = Z.text;
      const box = (st.box = el("div", "", wrap));
      box.style.cssText = `position:absolute;left:${tz.x}px;top:${tz.y}px;width:${tz.w}px;height:${tz.h}px;display:flex;flex-direction:column;align-items:center;justify-content:${tz.mid ? "center" : "flex-start"}`;
      const avail = tz.w * 0.96, K0 = (c.P ? 200 : 150) * u;
      st.tokens = [];
      const rowsEl = lines.map((toks) => {
        const hasKey = toks.some((t) => t.kind === "key" || t.kind === "acc" || t.kind === "num");
        const row = el("div", "", box);
        row.style.cssText = "display:flex;justify-content:center;align-items:baseline;white-space:nowrap";
        const spans = toks.map((tk) => {
          const sp = el("span", "", row, L.esc(tk.kind === "key" || tk.kind === "acc" || tk.kind === "num" ? tk.text.toUpperCase() : tk.text));
          const ratio = (hasKey ? SIZE : SIZE_NOKEY)[tk.kind];
          const base = (hasKey ? K0 : K0 * 0.5) * ratio;
          const heavy = tk.kind === "key" || tk.kind === "acc" || tk.kind === "num";
          sp.style.cssText = `display:inline-block;font:${heavy ? 800 : tk.kind === "it" ? 500 : 400} ${base}px/1 ${tk.kind === "it" ? "var(--serif)" : "var(--display)"};${tk.kind === "it" ? "font-style:italic;" : ""}letter-spacing:${heavy ? "-0.02em" : "-0.01em"};opacity:0;visibility:hidden`;
          const o = { sp, tk, base, color: finalColor(tk.kind, p.number_color === "ink"), heavy };
          st.tokens.push(o);
          return o;
        });
        return { row, spans, hasKey };
      });
      /* fit each line to the width, then the whole stack to its zone */
      rowsEl.forEach((r) => {
        const gap0 = 0.24 * Math.max(...r.spans.map((s) => s.base));
        const total = r.spans.reduce((a, s) => a + s.sp.offsetWidth, 0) + gap0 * (r.spans.length - 1);
        const k = Math.min(1, avail / total);
        r.k = k; r.gap = gap0 * k;
        r.spans.forEach((s) => { s.sp.style.fontSize = s.base * k + "px"; });
        r.row.style.columnGap = r.gap + "px";
      });
      const lineGap = 0.06 * K0;
      const stackH = () => rowsEl.reduce((a, r) => a + r.row.offsetHeight, 0) + lineGap * Math.max(0, rowsEl.length - 1);
      const fit = Math.min(1, tz.h / Math.max(1, stackH()));
      if (fit < 1) rowsEl.forEach((r) => { r.spans.forEach((s) => { s.sp.style.fontSize = s.base * r.k * fit + "px"; }); r.row.style.columnGap = r.gap * fit + "px"; });
      box.style.rowGap = lineGap * fit + "px";
      st.times = schedule(lines, c.words, c.dur);
      /* the element */
      const eo_ = p[elKind] || {};
      const tKey = st.tokens.findIndex((t) => t.tk.kind === "key" || t.tk.kind === "acc");
      /* a pill lands on its key word; a card, orbit or hero arrives with the first word so the lower frame is never empty for long */
      const defAt = !st.times.length ? 0.3 : elKind === "pill" ? st.times[tKey >= 0 ? tKey : Math.floor(st.times.length / 2)] : st.times[0];
      const wt = eo_.word ? L.wordTime(c, eo_.word) : null;
      st.elAt = wt != null ? Math.max(0, wt - 0.08) : eo_.at != null ? +eo_.at : Math.max(0.1, defAt + 0.05);
      st.elKind = elKind;
      if (elKind === "card") st.el = buildCard(wrap, c, Z.el, eo_);
      else if (elKind === "pill") {
        /* a pill is small: centre the words + pill as one group (slightly above middle) so the lower frame is not left empty */
        let top = tz.y;
        if (c.P) { top = c.safe.y + Math.max(0, (c.safe.h - (stackH() + 220 * u)) / 2) * 0.82; box.style.top = top + "px"; }
        st.el = buildPill(wrap, c, Z.el, { ...eo_, top: top + stackH() + 70 * u });
      }
      else if (elKind === "orbit") st.el = buildOrbit(wrap, c, Z.el, eo_);
      else if (elKind === "hero") st.el = buildHero(wrap, c, Z.el, eo_);
      if (p.handle) {
        const h = (st.handle = el("div", "", wrap, L.esc(p.handle)));
        h.style.cssText = `position:absolute;left:${c.safe.x}px;width:${c.safe.w}px;top:${c.safe.y + c.safe.h - 54 * u}px;text-align:center;font:500 ${30 * u}px/1 var(--display);letter-spacing:.04em;color:${C.ink};opacity:.34`;
        h.dataset.nolint = "";
      }
      return st;
    },
    update(st, tIn, c) {
      const p = c.p, u = c.u;
      const lt = realT(tIn, c);
      const t = c.index === 0 ? tIn : lt;
      const g = grey();
      st.tokens.forEach((q, i) => {
        const t0 = st.times[i], pp = seg(t, t0, t0 + 0.34), e = L.expo(pp);
        const k = L.eo(seg(t, t0, t0 + 0.28));
        const s = q.sp.style;
        s.opacity = clamp(pp * 2.2).toFixed(3);
        s.visibility = pp <= 0 ? "hidden" : "visible";
        s.transform = `translateY(${((1 - e) * 24 * u).toFixed(2)}px)`;
        s.filter = e < 0.999 ? `blur(${((1 - e) * 7).toFixed(2)}px)` : "";
        s.color = k >= 1 ? q.color : L.mix(g, q.color.startsWith("#") ? q.color : C.ink, k);
      });
      if (st.el) st.el.at(t, st.elAt, c.dur);
      /* the heavy-blur between sections: a few frames in and out, on the whole scene */
      const bin = c.index === 0 || p.blur_in === 0 ? 0 : p.blur_in != null ? +p.blur_in : (c.theme && c.theme.layout && c.theme.layout.blur_cut != null ? +c.theme.layout.blur_cut : 0.1);
      const bout = p.blur_out === 0 ? 0 : p.blur_out != null ? +p.blur_out : bin || 0.1;
      const qi = bin > 0 ? 1 - seg(lt, 0, bin) : 0, qo = bout > 0 ? seg(lt, c.dur - bout, c.dur) : 0;
      const bl = Math.max(qi, qo) * 30 * u;
      st.wrap.style.filter = bl > 0.05 ? `blur(${bl.toFixed(2)}px)` : "";
      st.wrap.style.opacity = (1 - 0.45 * Math.max(qi, qo)).toFixed(3);
    },
    cues(c) {
      const p = c.p, out = [];
      const lines = parse(p), times = schedule(lines, c.words, c.dur), toks = lines.flat();
      const elKind = p.element || (p.card ? "card" : p.pill ? "pill" : p.orbit ? "orbit" : p.hero ? "hero" : "none");
      const eo_ = p[elKind] || {};
      if (c.index > 0 && (p.blur_in !== 0)) out.push({ lt: 0, type: "whoosh", lvl: 2 });
      groups(times).forEach((gr) => out.push({ lt: gr.t, type: toks[gr.first] && (toks[gr.first].kind === "key" || toks[gr.first].kind === "acc") ? "pop" : "tick", lvl: 1 }));
      const tKey = toks.findIndex((t) => t.kind === "key" || t.kind === "acc");
      const defAt = times.length ? times[tKey >= 0 ? tKey : Math.floor(times.length / 2)] : 0.3;
      const wt = eo_.word ? L.wordTime(c, eo_.word) : null;
      const at = wt != null ? Math.max(0, wt - 0.08) : eo_.at != null ? +eo_.at : Math.max(0.1, defAt + 0.05);
      if (elKind !== "none") out.push({ lt: Math.max(0, at - 0.1), type: "whoosh", lvl: 2 });
      if (p.boom) {
        const b = typeof p.boom === "object" ? p.boom : {};
        const bw = b.word ? L.wordTime(c, b.word) : null;
        out.push({ lt: bw != null ? bw : b.at != null ? +b.at : elKind !== "none" ? at : 0, type: "boom", lvl: 3 });
      }
      return out;
    },
  };
})();
