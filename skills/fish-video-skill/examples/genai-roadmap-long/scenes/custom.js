/* Long-format roadmap scenes. Every update is a pure function of t.
   Reveals land on a spoken word (`word`), else at `at` seconds, else are spread evenly across the scene. */
(function () {
  "use strict";
  const S = (window.SCENES = window.SCENES || {});
  const { el, seg, eo, clamp } = L;
  const AMBER = "#f2b722";
  const INK = "#f5f5f5";
  const MUTED = "#b9bcc4";
  const PANEL = "#191a1e";

  const accent = (txt) => L.esc(String(txt)).replace(/\*([^*]+)\*/g, `<span style="color:${AMBER}">$1</span>`).replace(/\\n|\n/g, "<br>");
  function ground(root, c) {
    const g = el("div", "abs", root); L.pos(g, 0, 0, c.W, c.H);
    const s = 56 * c.u;
    g.style.cssText += `;background-color:#0f0f10;background-image:radial-gradient(ellipse at 50% 40%,rgba(242,183,34,.13),transparent 62%),linear-gradient(rgba(255,255,255,.055) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.055) 1px,transparent 1px);background-size:100% 100%,${s}px ${s}px,${s}px ${s}px`;
    return g;
  }
  function browser(parent, src, url, w, h, u) {
    const b = el("div", "abs", parent); L.pos(b, 0, 0, w, h); b.dataset.nolint = "";
    b.style.cssText += `;border-radius:${14 * u}px;overflow:hidden;background:#17181b;box-shadow:0 ${26 * u}px ${70 * u}px rgba(0,0,0,.7),0 0 0 ${2 * u}px rgba(255,255,255,.18)`;
    const bar = el("div", "abs", b); const bh = 44 * u; L.pos(bar, 0, 0, w, bh);
    bar.style.cssText += `;background:#26282d;display:flex;align-items:center;gap:${9 * u}px;padding-left:${16 * u}px;box-sizing:border-box`;
    ["#ff5f57", "#febc2e", "#28c840"].forEach((k) => { const d = el("div", "", bar); d.style.cssText = `width:${13 * u}px;height:${13 * u}px;border-radius:50%;background:${k};flex:none`; });
    const a = el("div", "", bar, L.esc(url)); a.style.cssText = `margin-left:${14 * u}px;padding:${5 * u}px ${18 * u}px;border-radius:${14 * u}px;background:#15161a;color:#c9cbd1;font:500 ${18 * u}px Inter,sans-serif;white-space:nowrap`;
    const box = el("div", "abs", b); L.pos(box, 0, bh, w, h - bh); box.style.overflow = "hidden";
    const img = el("img", "", box); img.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;object-position:top;transform-origin:50% 20%";
    L.setImg(img, L.projUrl(src));
    b.img = img;
    return b;
  }
  /* when an item appears: its spoken word, else `at`, else evenly spread across the scene */
  const when = (c, it, k, n, t0 = 0.25, t1) => {
    const w = it && it.word ? L.wordTime(c, it.word) : null;
    if (w != null) return w;
    if (it && it.at != null) return it.at;
    const end = t1 != null ? t1 : Math.max(t0 + 0.5, c.dur * 0.72);
    return t0 + (n > 1 ? (k * (end - t0)) / (n - 1) : 0);
  };
  const rise = (e, t, t0, d = 0.5, dist = 26, floor = 0) => { const p = eo(seg(t, t0, t0 + d)); e.style.opacity = floor + (1 - floor) * p; e.style.transform = `translateY(${(1 - p) * dist}px)`; };
  function heading(root, c, p, top) {
    const u = c.u, st = {};
    if (p.kicker) { st.k = el("div", "abs", root, L.esc(p.kicker)); L.pos(st.k, c.safe.x, top); st.k.style.cssText += `;padding:${10 * u}px ${20 * u}px;border-radius:${10 * u}px;background:${AMBER};color:#0f0f10;font:900 ${28 * u}px Inter,sans-serif;letter-spacing:.03em;white-space:nowrap`; top += 76 * u; }
    if (p.title) { st.h = el("div", "abs", root, accent(p.title)); L.pos(st.h, c.safe.x, top, c.safe.w); st.h.style.cssText += `;color:${INK};font:900 ${(p.title_size || 66) * u}px/1.08 Inter,sans-serif;letter-spacing:-.02em`; top += ((p.title_size || 66) * 1.2 + 16) * u; }
    st.bottom = top;
    return st;
  }
  const headingAt = (st, t) => { if (st.k) rise(st.k, t, 0, 0.4); if (st.h) rise(st.h, t, 0.06, 0.5); };

  /* ----- pile: real websites land big one by one and bury the viewer, then a line lands ----- */
  S.pile = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { cards: [], chips: [] };
      ground(root, c);
      (p.chips || []).forEach((tx, i) => {
        const d = el("div", "abs", root, L.esc(tx));
        const q = L.rng(i + 11);
        const fx = (i * 0.618 + 0.07) % 1, fy = (i * 0.381 + 0.11) % 1;
        L.pos(d, c.safe.x + (c.safe.w - 300 * u) * fx, c.safe.y + (c.safe.h - 80 * u) * fy);
        d.style.cssText += `;padding:${10 * u}px ${22 * u}px;border-radius:${40 * u}px;border:${2 * u}px solid rgba(242,183,34,.65);color:${AMBER};background:rgba(15,15,16,.86);font:700 ${30 * u}px Inter,sans-serif;white-space:nowrap`;
        st.chips.push({ d, t0: 0.15 + i * (p.chip_every || 0.3), rot: (q() - 0.5) * 12 });
      });
      const n = (p.cards || []).length;
      (p.cards || []).forEach((it, k) => {
        const w = (it.w || 0.5) * c.W, h = w * 0.66;
        const wrap = el("div", "abs", root); L.pos(wrap, it.x * c.W - w / 2, it.y * c.H - h / 2, w, h);
        browser(wrap, it.src, it.url, w, h, u);
        const tl = when(c, it, k, n, 0, p.title ? Math.max(0.3, (L.wordTime(c, p.title_word || "") ?? c.dur - 1.4) - 0.5) : c.dur - 1);
        st.cards.push({ wrap, it, w, t0: k === 0 ? -0.6 : tl });
      });
      st.cards.forEach((s, k) => { const nx = st.cards[k + 1]; s.settle = nx ? nx.t0 : s.t0 + 0.42 + (p.hold_last || 0); s.dx = (0.5 - s.it.x) * c.W; s.dy = (0.5 - s.it.y) * c.H; s.big = (0.74 * c.W) / s.w; });
      st.chips.forEach((x) => root.appendChild(x.d));
      st.tt = p.title ? (L.wordTime(c, p.title_word || "") ?? c.dur - 1.4) : 1e9;
      if (p.title) {
        const sc = (st.scrim = el("div", "abs", root)); L.pos(sc, 0, 0, c.W, c.H); sc.style.background = "rgba(8,8,9,.74)";
        const T = (st.T = el("div", "abs", root, accent(p.title)));
        L.pos(T, c.safe.x + 80 * u, c.H * 0.27, c.safe.w - 160 * u, c.H * 0.46);
        T.style.cssText += `;display:flex;align-items:center;justify-content:center;text-align:center;color:#fff;font:900 ${(p.title_size || 150) * u}px/1.02 Inter,sans-serif;letter-spacing:-.03em;text-shadow:0 ${8 * u}px ${40 * u}px #000`;
      }
      return st;
    },
    update(st, t, c) {
      for (const s of st.chips) { const a = L.back(seg(t, s.t0, s.t0 + 0.28), 1.8); s.d.style.opacity = eo(seg(t, s.t0, s.t0 + 0.1)); s.d.style.transform = `rotate(${s.rot}deg) scale(${a})`; }
      for (const s of st.cards) {
        const a = eo(seg(t, s.t0, s.t0 + 0.25));
        const m = eo(seg(t, s.settle, s.settle + 0.3));
        s.wrap.style.opacity = a;
        s.wrap.style.transform = `translate(${s.dx * (1 - m)}px,${s.dy * (1 - m) + (t - s.t0) * 3 * c.u}px) rotate(${(s.it.rot || 0) * m}deg) scale(${(s.big + (1 - s.big) * m) * (1.15 - 0.15 * a)})`;
      }
      if (st.T) { const q = eo(seg(t, st.tt, st.tt + 0.3)); st.scrim.style.opacity = q; st.T.style.opacity = q; st.T.style.transform = `scale(${1.05 - 0.05 * q + Math.max(0, t - st.tt) * 0.004})`; }
    },
    cues: (c) => {
      const out = [], n = (c.p.cards || []).length;
      const end = c.p.title ? Math.max(0.3, (L.wordTime(c, c.p.title_word || "") ?? c.dur - 1.4) - 0.5) : c.dur - 1;
      (c.p.cards || []).forEach((it, k) => { if (k) out.push({ lt: when(c, it, k, n, 0, end), type: "thump", lvl: 2 }); });
      if (c.p.title) out.push({ lt: L.wordTime(c, c.p.title_word || "") ?? c.dur - 1.4, type: c.p.title_cue || "swell", lvl: 3 });
      return out;
    },
  };

  /* ----- roadmap: the recurring character. Serpentine map; the camera flies stop to stop and lands on spoken words ----- */
  S.roadmap = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { nodes: [] };
      ground(root, c);
      const world = (st.world = el("div", "abs", root)); world.dataset.nolint = ""; L.pos(world, 0, 0, c.W, c.H); world.style.transformOrigin = "0 0";
      const NW = 470 * u, NH = 350 * u, DX = 610 * u, DY = 500 * u, cols = p.cols || 4;
      st.NW = NW; st.NH = NH;
      st.pts = (p.nodes || []).map((_, i) => { const row = Math.floor(i / cols); const col = row % 2 ? cols - 1 - (i % cols) : i % cols; return { X: col * DX, Y: row * DY }; });
      const svg = L.svg("svg", { width: 10, height: 10 }, world); svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible";
      const pts = st.pts.map((q) => `${q.X},${q.Y}`).join(" ");
      L.svg("polyline", { points: pts, fill: "none", stroke: "rgba(255,255,255,.2)", "stroke-width": 5 * u, "stroke-dasharray": `${10 * u} ${14 * u}` }, svg);
      st.line = L.svg("polyline", { points: pts, fill: "none", stroke: AMBER, "stroke-width": 9 * u, "stroke-linecap": "round", filter: "url(#fv-bloom)" }, svg);
      st.seg = st.pts.slice(1).map((q, i) => Math.hypot(q.X - st.pts[i].X, q.Y - st.pts[i].Y));
      st.len = st.seg.reduce((a, b) => a + b, 0);
      st.line.setAttribute("stroke-dasharray", `${st.len} ${st.len}`);
      st.dot = L.svg("circle", { r: 16 * u, fill: "#fff", filter: "url(#fv-bloom)" }, svg);
      (p.nodes || []).forEach((n, i) => {
        const q = st.pts[i], d = el("div", "abs", world); L.pos(d, q.X - NW / 2, q.Y - NH / 2, NW, NH);
        d.style.cssText += `;box-sizing:border-box;border-radius:${22 * u}px;background:${PANEL};border:${3 * u}px solid rgba(255,255,255,.22);overflow:hidden;box-shadow:0 ${20 * u}px ${50 * u}px rgba(0,0,0,.6)`;
        const im = el("div", "abs", d); L.pos(im, 0, 0, NW, NH * 0.56); im.style.overflow = "hidden"; im.style.background = "#26282d";
        if (n.src) { const img = el("img", "", im); img.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;object-position:top"; L.setImg(img, L.projUrl(n.src)); }
        else { const ic = el("div", "abs", im, L.esc(n.glyph || "")); L.pos(ic, 0, 0, NW, NH * 0.56); ic.style.cssText += `;display:flex;align-items:center;justify-content:center;color:${AMBER};font:800 ${58 * u}px 'JetBrains Mono',monospace`; }
        const tag = el("div", "abs", d, L.esc(n.tag)); L.pos(tag, 22 * u, NH * 0.6); tag.style.cssText += `;color:${AMBER};font:800 ${25 * u}px Inter,sans-serif;letter-spacing:.09em`;
        const lb = el("div", "abs", d, L.esc(n.label)); L.pos(lb, 22 * u, NH * 0.71, NW - 44 * u); lb.style.cssText += `;color:#fff;font:800 ${44 * u}px/1.05 Inter,sans-serif;letter-spacing:-.015em`;
        st.nodes.push({ d, i });
      });
      if (p.kicker) { const k = (st.k = el("div", "abs", root, L.esc(p.kicker))); L.pos(k, c.safe.x, c.safe.y); k.style.cssText += `;padding:${12 * u}px ${24 * u}px;border-radius:${12 * u}px;background:${AMBER};color:#0f0f10;font:900 ${34 * u}px Inter,sans-serif;letter-spacing:.02em;white-space:nowrap`; }
      if (p.cta) { const a = (st.cta = el("div", "abs", root, `<span>${accent(p.cta)}</span>`)); L.pos(a, c.safe.x, c.H - c.safe.y - 110 * u - (c.H - c.safe.y - c.safe.h), c.safe.w, 90 * u); a.style.cssText += `;display:flex;align-items:center;justify-content:center;color:#fff;font:900 ${60 * u}px Inter,sans-serif;letter-spacing:-.02em;text-shadow:0 ${4 * u}px ${24 * u}px #000`; }
      st.V = (p.visits || [{ i: 0, t: 0 }]).map((v) => ({ i: v.i, t: v.word ? (L.wordTime(c, v.word) ?? v.t ?? 0) : v.t || 0 }));
      st.pull = p.pull_word ? L.wordTime(c, p.pull_word) : p.pull_at;
      return st;
    },
    update(st, t, c) {
      const p = c.p, u = c.u, V = st.V;
      let i = 0; while (i < V.length - 1 && t >= V[i + 1].t) i++;
      const a = V[i], b = V[i + 1] || a, x = b === a ? 1 : L.expo(seg(t, Math.max(a.t, b.t - (p.move || 0.8)), b.t));
      const f = a.i + (b.i - a.i) * x;
      const pullOut = st.pull != null ? eo(seg(t, st.pull, st.pull + (p.pull_dur || 1))) : 0;
      const wideIn = p.open_wide ? 1 - eo(seg(t, 0.15, p.open_wide)) : 0;
      const po = Math.max(pullOut, wideIn);
      const zoomIn = p.zoom || 1.42, zoom = zoomIn + ((p.wide_zoom || 0.68) - zoomIn) * po;
      const idx = clamp(Math.floor(f), 0, st.pts.length - 2), fr = f - idx;
      const X = st.pts[idx].X + (st.pts[idx + 1].X - st.pts[idx].X) * fr, Y = st.pts[idx].Y + (st.pts[idx + 1].Y - st.pts[idx].Y) * fr;
      const done = st.seg.slice(0, idx).reduce((m, n) => m + n, 0) + st.seg[idx] * fr;
      const allOn = p.reveal_all ? pullOut : 0;
      st.line.setAttribute("stroke-dashoffset", st.len - (done + (st.len - done) * allOn));
      st.dot.setAttribute("cx", X); st.dot.setAttribute("cy", Y);
      const xs = st.pts.map((q) => q.X), ys = st.pts.map((q) => q.Y);
      const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      const midX = (x0 + x1) / 2, midY = (y0 + y1) / 2 - 8 * u;
      /* clamp: never let the camera look past the map, so a frame edge is never bare grid */
      const hw = c.W / 2 / zoom, hh = c.H / 2 / zoom, mX = st.NW / 2 + 40 * u, mY = st.NH / 2 + 40 * u;
      const clampTo = (v, lo, hi, m) => (lo > hi ? m : clamp(v, lo, hi));
      const cX = clampTo(X, x0 - mX + hw, x1 + mX - hw, midX), cY = clampTo(Y, y0 - mY + hh, y1 + mY - hh, midY);
      const cx = cX + (midX - cX) * po, cy = cY + (midY - cY) * po;
      st.world.style.transform = `translate(${c.W / 2 - cx * zoom}px,${c.H / 2 - cy * zoom}px) scale(${zoom})`;
      for (const n of st.nodes) {
        const lit = f >= n.i - 0.06 || allOn * (st.nodes.length - 1) >= n.i;
        const here = Math.abs(f - n.i) < 0.5 && !allOn;
        n.d.style.borderColor = lit ? AMBER : "rgba(255,255,255,.22)";
        n.d.style.boxShadow = lit ? `0 0 ${(here ? 70 : 34) * u}px rgba(242,183,34,${here ? 0.6 : 0.3})` : `0 ${20 * u}px ${50 * u}px rgba(0,0,0,.6)`;
        n.d.style.opacity = lit || po > 0.3 ? 1 : 0.78;
      }
      if (st.k) st.k.style.opacity = eo(seg(po, 0.35, 0.75));
      if (st.cta) { const k = st.pull != null ? st.pull + 0.6 : 0.5; rise(st.cta, t, p.cta_word ? (L.wordTime(c, p.cta_word) ?? k) : k, 0.5); }
    },
    cues: (c) => {
      const p = c.p, out = [{ lt: 0, type: "swish", lvl: 2 }];
      (p.visits || []).slice(1).forEach((v) => { const tt = v.word ? (L.wordTime(c, v.word) ?? v.t ?? 0) : v.t || 0; out.push({ lt: Math.max(0, tt - 0.5), type: "whoosh", lvl: 2 }); out.push({ lt: tt, type: "zap", lvl: 2 }); });
      const pull = p.pull_word ? L.wordTime(c, p.pull_word) : p.pull_at;
      if (pull != null) { out.push({ lt: pull, type: "whoosh", lvl: 2 }); out.push({ lt: pull + (p.pull_dur || 1), type: "chime", lvl: 3 }); }
      return out;
    },
  };

  /* ghost map behind big lines, so a statement frame is never bare */
  function ghostMap(root, c) {
    const u = c.u, g = el("div", "abs", root); L.pos(g, 0, 0, c.W, c.H); g.style.opacity = 0.22; g.dataset.nolint = "";
    const svg = L.svg("svg", { width: c.W, height: c.H }, g); svg.style.cssText = "position:absolute;left:0;top:0";
    const xs = [0.12, 0.37, 0.63, 0.88], ys = [0.2, 0.8];
    const P = [...xs.map((x) => [x, ys[0]]), ...xs.slice().reverse().map((x) => [x, ys[1]])].map(([x, y]) => [x * c.W, y * c.H]);
    L.svg("polyline", { points: P.map((q) => q.join(",")).join(" "), fill: "none", stroke: AMBER, "stroke-width": 5 * u }, svg);
    P.forEach((q) => L.svg("rect", { x: q[0] - 150 * u, y: q[1] - 100 * u, width: 300 * u, height: 200 * u, rx: 18 * u, fill: "#191a1e", stroke: AMBER, "stroke-width": 3 * u }, svg));
    return g;
  }

  /* ----- statement: big calm lines over the ghost map ----- */
  S.statement = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { lines: [] };
      ground(root, c); st.g = ghostMap(root, c);
      const b = el("div", "abs", root); L.pos(b, c.safe.x + 50 * u, c.safe.y, c.safe.w - 100 * u, c.safe.h);
      b.style.cssText += "display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center";
      (p.lines || []).forEach((tx, i) => {
        const it = typeof tx === "string" ? { text: tx } : tx;
        const e = el("div", "", b, accent(it.text));
        e.style.cssText = `color:#fff;font:900 ${(it.size || p.size || 92) * u}px/1.1 Inter,sans-serif;letter-spacing:-.025em;margin:${16 * u}px 0;text-shadow:0 ${6 * u}px ${30 * u}px #000`;
        st.lines.push({ e, it, k: i });
      });
      const n = st.lines.length; st.lines.forEach((s) => { s.t0 = s.k === 0 ? -1 : when(c, s.it, s.k, n, 0, Math.max(0.6, c.dur * 0.62)); });
      return st;
    },
    update(st, t, c) {
      st.lines.forEach((s) => rise(s.e, t, s.t0, 0.55, 30 * c.u));
      st.g.style.transform = `scale(${1.02 + t * 0.006})`;
    },
    cues: (c) => { const n = (c.p.lines || []).length; return (c.p.lines || []).slice(1).map((it, k) => ({ lt: when(c, typeof it === "string" ? {} : it, k + 1, n, 0, Math.max(0.6, c.dur * 0.62)), type: "swish", lvl: 2 })); },
  };

  /* ----- site: real website(s) in a browser with notes landing beside it ----- */
  S.site = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { shots: [], notes: [] };
      ground(root, c);
      const shots = p.shots || [{ src: p.src, url: p.url }];
      const gap = 56 * u, w = Math.min(c.safe.w * 0.62, 1040 * u), h = Math.min(c.safe.h * 0.94, w * 0.68), x = c.safe.x, y = c.safe.y + (c.safe.h - h) / 2;
      shots.forEach((sh, k) => {
        const wrap = el("div", "abs", root); L.pos(wrap, x, y, w, h);
        const br = browser(wrap, sh.src, sh.url, w, h, u);
        st.shots.push({ wrap, br, t0: k === 0 ? -1 : when(c, sh, k, shots.length, 0.4, c.dur * 0.72), k });
      });
      const cx = x + w + gap, cw = c.safe.x + c.safe.w - cx;
      const col = el("div", "abs", root); L.pos(col, cx, c.safe.y, cw, c.safe.h);
      col.style.cssText += `;display:flex;flex-direction:column;justify-content:center;gap:${24 * u}px`;
      if (p.kicker) { st.k = el("div", "", col, L.esc(p.kicker)); st.k.style.cssText = `align-self:flex-start;padding:${10 * u}px ${20 * u}px;border-radius:${10 * u}px;background:${AMBER};color:#0f0f10;font:900 ${28 * u}px Inter,sans-serif;letter-spacing:.03em;white-space:nowrap`; }
      if (p.title) { st.h = el("div", "", col, accent(p.title)); st.h.style.cssText = `color:#fff;font:900 ${(p.title_size || 68) * u}px/1.06 Inter,sans-serif;letter-spacing:-.02em`; }
      const notes = p.notes || [];
      notes.forEach((nt, k) => {
        const it = typeof nt === "string" ? { text: nt } : nt;
        const e = el("div", "", col, accent(it.text));
        e.style.cssText = `padding:${14 * u}px ${20 * u}px;border-left:${6 * u}px solid ${AMBER};background:rgba(25,26,30,.92);border-radius:${8 * u}px;color:${INK};font:600 ${34 * u}px/1.22 Inter,sans-serif`;
        st.notes.push({ e, t0: when(c, it, k, notes.length, 0.5, c.dur * 0.8) });
      });
      return st;
    },
    update(st, t, c) {
      if (st.k) rise(st.k, t, -0.3, 0.3); if (st.h) rise(st.h, t, -0.2, 0.4);
      for (const s of st.shots) {
        const a = eo(seg(t, s.t0, s.t0 + 0.45));
        s.wrap.style.opacity = s.k === 0 ? 1 : a;
        s.wrap.style.transform = s.k === 0 ? "" : `translateY(${(1 - a) * 60 * c.u}px) scale(${0.97 + 0.03 * a})`;
        s.br.img.style.transform = `scale(${1 + Math.max(0, t - s.t0) * 0.006})`;
      }
      for (const s of st.notes) rise(s.e, t, s.t0, 0.45, 18 * c.u);
    },
    cues: (c) => {
      const out = [{ lt: 0, type: "swish", lvl: 2 }], p = c.p;
      (p.shots || []).slice(1).forEach((sh, k) => out.push({ lt: when(c, sh, k + 1, p.shots.length, 0.4, c.dur * 0.72), type: "thump", lvl: 2 }));
      return out;
    },
  };

  /* ----- cards: a grid of ideas, each landing on its word; the newest is lit ----- */
  S.cards = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { cards: [] };
      ground(root, c); st.head = heading(root, c, p, c.safe.y);
      const items = p.items || [], n = items.length, cols = p.cols || (n <= 3 ? n : n === 4 ? 2 : 3), rows = Math.ceil(n / cols), g = 26 * u;
      const top = st.head.bottom + 10 * u, H = c.safe.y + c.safe.h - top, cw = (c.safe.w - g * (cols - 1)) / cols, ch = Math.min((H - g * (rows - 1)) / rows, (p.max_h || 420) * u);
      const y0 = top + Math.max(0, (H - rows * ch - g * (rows - 1)) / 2);
      items.forEach((it, k) => {
        const e = el("div", "abs", root); L.pos(e, c.safe.x + (k % cols) * (cw + g), y0 + Math.floor(k / cols) * (ch + g), cw, ch);
        e.style.cssText += `;box-sizing:border-box;padding:${24 * u}px ${28 * u}px;border-radius:${20 * u}px;background:${PANEL};border:${3 * u}px solid rgba(255,255,255,.2);display:flex;flex-direction:column;justify-content:center;gap:${12 * u}px;overflow:hidden`;
        if (it.tag) { const q = el("div", "", e, L.esc(it.tag)); q.style.cssText = `color:${AMBER};font:800 ${30 * u}px 'JetBrains Mono',monospace;letter-spacing:.04em`; }
        const b = el("div", "", e, accent(it.t)); b.style.cssText = `color:#fff;font:800 ${(p.t_size || 54) * u}px/1.08 Inter,sans-serif;letter-spacing:-.015em`;
        if (it.d) { const d = el("div", "", e, accent(it.d)); d.style.cssText = `color:${MUTED};font:500 ${(p.d_size || 36) * u}px/1.25 Inter,sans-serif`; }
        st.cards.push({ e, t0: when(c, it, k, n, 0.2, c.dur * 0.78) });
      });
      return st;
    },
    update(st, t, c) {
      headingAt(st.head, t + 0.4);
      st.cards.forEach((s, k) => {
        const a = eo(seg(t, s.t0, s.t0 + 0.45)), nx = st.cards[k + 1];
        s.e.style.opacity = 0.45 + 0.55 * a; s.e.style.transform = `translateY(${(1 - a) * 10 * c.u}px)`;
        const hot = t >= s.t0 && (!nx || t < nx.t0);
        s.e.style.borderColor = hot ? AMBER : "rgba(255,255,255,.2)";
        s.e.style.boxShadow = hot ? `0 0 ${40 * c.u}px rgba(242,183,34,.42)` : "none";
      });
    },
    cues: (c) => (c.p.items || []).map((it, k, a) => ({ lt: when(c, it, k, a.length, 0.2, c.dur * 0.78), type: "swish", lvl: 2 })),
  };

  /* ----- flow: a pipeline of boxes joined by glowing arrows, each landing on its word ----- */
  S.flow = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { nodes: [], arrows: [] };
      ground(root, c); st.head = heading(root, c, p, c.safe.y);
      const items = p.nodes || [], n = items.length, g = 96 * u, w = (c.safe.w - g * (n - 1)) / n, h = Math.min(c.safe.h * 0.56, (p.h || 430) * u);
      const top = st.head.bottom, y = top + (c.safe.y + c.safe.h - top - h) / 2;
      const svg = L.svg("svg", { width: c.W, height: c.H }, root); svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible";
      items.forEach((it, k) => {
        const x = c.safe.x + k * (w + g);
        const e = el("div", "abs", root); L.pos(e, x, y, w, h);
        e.style.cssText += `;box-sizing:border-box;padding:${26 * u}px;border-radius:${22 * u}px;background:${PANEL};border:${3 * u}px solid rgba(255,255,255,.22);display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:${16 * u}px;overflow:hidden`;
        if (it.glyph) { const q = el("div", "", e, L.esc(it.glyph)); q.style.cssText = `color:${AMBER};font:800 ${(it.glyph_size || 64) * u}px 'JetBrains Mono',monospace`; }
        const b = el("div", "", e, accent(it.label)); b.style.cssText = `color:#fff;font:800 ${(p.size || 46) * u}px/1.08 Inter,sans-serif;letter-spacing:-.015em`;
        if (it.sub) { const d = el("div", "", e, accent(it.sub)); d.style.cssText = `color:${MUTED};font:500 ${32 * u}px/1.24 Inter,sans-serif`; }
        st.nodes.push({ e, t0: when(c, it, k, n, 0.2, c.dur * 0.75) });
        if (k < n - 1) {
          const x1 = x + w + 10 * u, x2 = x + w + g - 12 * u, ym = y + h / 2;
          const ln = L.svg("line", { x1, y1: ym, x2, y2: ym, stroke: AMBER, "stroke-width": 7 * u, filter: "url(#fv-bloom)", "stroke-linecap": "round" }, svg);
          const hd = L.svg("path", { d: `M${x2 - 18 * u} ${ym - 16 * u} L${x2} ${ym} L${x2 - 18 * u} ${ym + 16 * u}`, fill: "none", stroke: AMBER, "stroke-width": 7 * u, "stroke-linecap": "round" }, svg);
          st.arrows.push({ ln, hd, x1, x2, k });
        }
      });
      return st;
    },
    update(st, t, c) {
      headingAt(st.head, t + 0.4);
      st.nodes.forEach((s, k) => {
        const a = eo(seg(t, s.t0, s.t0 + 0.45)), nx = st.nodes[k + 1], hot = t >= s.t0 && (!nx || t < nx.t0);
        s.e.style.opacity = 0.45 + 0.55 * a; s.e.style.transform = `scale(${0.97 + 0.03 * a})`;
        s.e.style.borderColor = t >= s.t0 ? AMBER : "rgba(255,255,255,.22)";
        s.e.style.boxShadow = hot ? `0 0 ${50 * c.u}px rgba(242,183,34,.5)` : "none";
      });
      st.arrows.forEach((r) => {
        const t0 = st.nodes[r.k + 1].t0 - 0.35, p = eo(seg(t, t0, t0 + 0.35));
        r.ln.setAttribute("x2", r.x1 + (r.x2 - r.x1) * p); r.ln.style.opacity = p > 0 ? 1 : 0; r.hd.style.opacity = p >= 0.98 ? 1 : 0;
      });
    },
    cues: (c) => (c.p.nodes || []).map((it, k, a) => ({ lt: when(c, it, k, a.length, 0.2, c.dur * 0.75), type: k ? "zap" : "swish", lvl: 2 })),
  };

  /* ----- attention: a sentence; one word reaches back to the words that explain it ----- */
  S.attention = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { w: [] };
      ground(root, c); st.head = heading(root, c, p, c.safe.y);
      const box = (st.box = el("div", "abs", root)); L.pos(box, c.safe.x + 30 * u, c.safe.y + c.safe.h * 0.42, c.safe.w - 60 * u, c.safe.h * 0.5);
      box.style.cssText += `;display:flex;flex-wrap:wrap;justify-content:center;align-content:flex-start;gap:${18 * u}px ${28 * u}px`;
      (p.sentence || []).forEach((tx) => { const s = el("span", "", box, L.esc(tx)); s.style.cssText = `position:relative;padding:${6 * u}px ${14 * u}px;border-radius:${12 * u}px;color:#fff;font:800 ${(p.size || 92) * u}px/1.1 Inter,sans-serif;letter-spacing:-.02em`; st.w.push(s); });
      st.svg = L.svg("svg", { width: c.W, height: c.H }, root); st.svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible;pointer-events:none";
      st.from = L.wordTime(c, p.from_word || "") ?? c.dur * 0.35;
      return st;
    },
    update(st, t, c) {
      const p = c.p, u = c.u; headingAt(st.head, t + 0.4);
      if (!st.arcs) {
        const base = st.box.getBoundingClientRect(), scale = base.width / st.box.offsetWidth || 1, ox = st.box.offsetLeft, oy = st.box.offsetTop;
        const pos = st.w.map((s) => { const r = s.getBoundingClientRect(); return { x: ox + (r.left - base.left + r.width / 2) / scale, y: oy + (r.top - base.top) / scale }; });
        st.arcs = (p.links || []).map((l) => {
          const a = pos[p.focus], b = pos[l.to], lift = 90 * u + Math.abs(a.x - b.x) * 0.1;
          const path = L.svg("path", { d: `M${a.x} ${a.y} C${a.x} ${a.y - lift},${b.x} ${b.y - lift},${b.x} ${b.y}`, fill: "none", stroke: AMBER, "stroke-width": 4 * u + 9 * u * l.weight, opacity: 0.25 + 0.75 * l.weight, "stroke-linecap": "round", filter: "url(#fv-bloom)" }, st.svg);
          const len = path.getTotalLength(); path.setAttribute("stroke-dasharray", `${len} ${len}`);
          return { path, len, l };
        });
      }
      const k = eo(seg(t, st.from, st.from + 0.5));
      st.w.forEach((s, i) => {
        const lk = (p.links || []).find((q) => q.to === i);
        const on = i === p.focus ? k : lk ? eo(seg(t, st.from + 0.5, st.from + 1.1)) * lk.weight : 0;
        s.style.background = i === p.focus ? `rgba(242,183,34,${k})` : `rgba(242,183,34,${on * 0.42})`;
        s.style.color = i === p.focus && k > 0.5 ? "#0f0f10" : "#fff";
        rise(s, t + 0.3, i * 0.03, 0.35, 10 * u);
      });
      st.arcs.forEach((a) => a.path.setAttribute("stroke-dashoffset", a.len * (1 - eo(seg(t, st.from + 0.3, st.from + 1.1)))));
    },
    cues: (c) => [{ lt: L.wordTime(c, c.p.from_word || "") ?? c.dur * 0.35, type: "zap", lvl: 2 }],
  };

  /* ----- versus: generator makes a picture, discriminator judges it, the picture sharpens each round ----- */
  S.versus = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = {};
      ground(root, c); st.head = heading(root, c, p, c.safe.y);
      const top = st.head.bottom + 10 * u, H = c.safe.y + c.safe.h - top, side = Math.min(H * 0.92, 500 * u), bw = (c.safe.w - side - 160 * u) / 2, by = top + (H - side) / 2;
      const mk = (x, tx, sub) => { const e = el("div", "abs", root); L.pos(e, x, by, bw, side); e.style.cssText += `;box-sizing:border-box;padding:${22 * u}px;border-radius:${22 * u}px;background:${PANEL};border:${3 * u}px solid ${AMBER};display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:${16 * u}px`; const b = el("div", "", e, L.esc(tx)); b.style.cssText = `color:#fff;font:800 ${46 * u}px/1.08 Inter,sans-serif`; const d = el("div", "", e, L.esc(sub)); d.style.cssText = `color:${MUTED};font:500 ${31 * u}px/1.24 Inter,sans-serif`; return { e, d }; };
      st.gen = mk(c.safe.x, p.left || "Generator", p.left_sub || "creates new data");
      st.dis = mk(c.safe.x + c.safe.w - bw, p.right || "Discriminator", p.right_sub || "judges if it looks real");
      const ix = c.safe.x + bw + 80 * u;
      const frame = (st.frame = el("div", "abs", root)); L.pos(frame, ix, by, side, side); frame.style.cssText += `;overflow:hidden;border-radius:${18 * u}px;box-shadow:0 0 0 ${3 * u}px rgba(255,255,255,.3)`;
      const im = (st.im = el("img", "", frame)); im.style.cssText = "position:absolute;inset:0;width:100%;height:100%;object-fit:cover"; L.setImg(im, L.projUrl(p.image));
      const v = (st.v = el("div", "", st.dis.e, "")); v.style.cssText = `padding:${10 * u}px ${22 * u}px;border-radius:${10 * u}px;font:900 ${42 * u}px Inter,sans-serif;letter-spacing:.03em`;
      const ar = L.svg("svg", { width: c.W, height: c.H }, root); ar.style.cssText = "position:absolute;left:0;top:0;overflow:visible";
      const ym = by + side / 2;
      st.a1 = L.svg("path", { d: `M${ix - 62 * u} ${ym} L${ix - 14 * u} ${ym} M${ix - 32 * u} ${ym - 16 * u} L${ix - 14 * u} ${ym} L${ix - 32 * u} ${ym + 16 * u}`, fill: "none", stroke: AMBER, "stroke-width": 7 * u, "stroke-linecap": "round" }, ar);
      const ex = ix + side;
      st.a2 = L.svg("path", { d: `M${ex + 14 * u} ${ym} L${ex + 62 * u} ${ym} M${ex + 44 * u} ${ym - 16 * u} L${ex + 62 * u} ${ym} L${ex + 44 * u} ${ym + 16 * u}`, fill: "none", stroke: AMBER, "stroke-width": 7 * u, "stroke-linecap": "round" }, ar);
      st.t = [L.wordTime(c, p.left_word || "") ?? 1, L.wordTime(c, p.right_word || "") ?? c.dur * 0.5, L.wordTime(c, p.real_word || "") ?? c.dur * 0.8];
      return st;
    },
    update(st, t, c) {
      headingAt(st.head, t + 0.4);
      const [t1, t2, t3] = st.t;
      st.gen.e.style.opacity = 0.45 + 0.55 * eo(seg(t, t1 - 0.6, t1)); st.frame.style.opacity = 0.45 + 0.55 * eo(seg(t, t1, t1 + 0.4)); st.a1.style.opacity = eo(seg(t, t1, t1 + 0.3));
      st.dis.e.style.opacity = 0.45 + 0.55 * eo(seg(t, t2 - 0.5, t2)); st.a2.style.opacity = eo(seg(t, t2 - 0.2, t2));
      const cl = eo(seg(t, t2, t3 + 0.8));
      st.im.style.filter = `blur(${(1 - cl) * 34 * c.u}px) contrast(${1.5 - 0.5 * cl})`;
      const real = t >= t3 + 0.4;
      st.v.textContent = real ? "REAL?" : t >= t2 ? "FAKE" : "";
      st.v.style.background = real ? AMBER : "#b3202a"; st.v.style.color = real ? "#0f0f10" : "#fff"; st.v.style.opacity = t >= t2 ? 1 : 0;
    },
    cues: (c) => { const p = c.p, a = L.wordTime(c, p.right_word || "") ?? c.dur * 0.5, b = L.wordTime(c, p.real_word || "") ?? c.dur * 0.8; return [{ lt: a, type: "thump", lvl: 2 }, { lt: b + 0.4, type: "chime", lvl: 3 }]; },
  };

  /* ----- hourglass: data squeezes through a narrow middle, then gets rebuilt (autoencoder) ----- */
  S.hourglass = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { dots: [] };
      ground(root, c); st.head = heading(root, c, p, c.safe.y);
      const top = st.head.bottom + 20 * u, H = c.safe.y + c.safe.h - top - 80 * u, mid = top + H / 2, x0 = c.safe.x + 120 * u, x1 = c.safe.x + c.safe.w - 120 * u, cx = (x0 + x1) / 2, hw = H / 2, nk = 56 * u;
      Object.assign(st, { mid, x0, x1, cx, hw, nk });
      const svg = L.svg("svg", { width: c.W, height: c.H }, root); svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible";
      L.svg("path", { d: `M${x0} ${mid - hw} L${cx - 60 * u} ${mid - nk} L${cx + 60 * u} ${mid - nk} L${x1} ${mid - hw} L${x1} ${mid + hw} L${cx + 60 * u} ${mid + nk} L${cx - 60 * u} ${mid + nk} L${x0} ${mid + hw} Z`, fill: "rgba(242,183,34,.09)", stroke: AMBER, "stroke-width": 4 * u, "stroke-linejoin": "round", filter: "url(#fv-bloom)" }, svg);
      const rng = L.rng(5);
      for (let i = 0; i < 90; i++) st.dots.push({ c: L.svg("circle", { r: (6 + rng() * 5) * u, fill: rng() < 0.2 ? "#fff" : AMBER }, svg), ph: rng(), v: rng(), sp: 0.1 + rng() * 0.04 });
      const lbl = (x, tx, sub) => { const e = el("div", "abs", root); L.pos(e, x - 240 * u, mid + hw + 8 * u, 480 * u); e.style.cssText += `;text-align:center;color:#fff;font:800 ${42 * u}px Inter,sans-serif`; e.innerHTML = accent(tx); return e; };
      st.labels = (p.labels || []).map((it, k) => ({ e: lbl(k === 0 ? x0 + 130 * u : k === 1 ? cx : x1 - 130 * u, it.t), t0: when(c, it, k, p.labels.length, 0.3, c.dur * 0.7) }));
      return st;
    },
    update(st, t, c) {
      headingAt(st.head, t + 0.4);
      for (const d of st.dots) {
        const f = (d.ph + t * d.sp) % 1, x = st.x0 + (st.x1 - st.x0) * f, e = Math.abs(f - 0.5) * 2;
        const open = st.nk * 0.8 + (st.hw * 0.9 - st.nk * 0.8) * e;
        d.c.setAttribute("cx", x); d.c.setAttribute("cy", st.mid + (d.v * 2 - 1) * open);
        d.c.setAttribute("opacity", 0.9);
      }
      st.labels.forEach((s) => rise(s.e, t, s.t0, 0.45, 14 * c.u));
    },
    cues: (c) => (c.p.labels || []).map((it, k, a) => ({ lt: when(c, it, k, a.length, 0.3, c.dur * 0.7), type: "swish", lvl: 2 })),
  };

  /* ----- meaning: a map of meaning. Similar words sit together; a question lands next to its match ----- */
  S.meaning = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { pts: [] };
      ground(root, c); st.head = heading(root, c, p, c.safe.y);
      const top = st.head.bottom, x0 = c.safe.x, y0 = top, W = c.safe.w, H = c.safe.y + c.safe.h - top;
      const svg = (st.svg = L.svg("svg", { width: c.W, height: c.H }, root)); svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible";
      (p.groups || []).forEach((g, gi) => {
        const cx = x0 + g.x * W, cy = y0 + g.y * H;
        const halo = L.svg("ellipse", { cx, cy, rx: 300 * u, ry: 165 * u, fill: "rgba(242,183,34,.08)", stroke: "rgba(242,183,34,.45)", "stroke-width": 3 * u, "stroke-dasharray": `${10 * u} ${10 * u}` }, svg);
        const t0 = when(c, g, gi, p.groups.length, 0.2, c.dur * 0.55);
        st.pts.push({ halo, t0 });
        (g.words || []).forEach((w, k) => {
          const a = (k / g.words.length) * Math.PI * 2 + gi, px = cx + Math.cos(a) * 170 * u, py = cy + Math.sin(a) * 72 * u;
          const e = el("div", "abs", root, L.esc(w)); L.pos(e, px - 110 * u, py - 24 * u, 220 * u); e.style.cssText += `;text-align:center;color:#fff;font:700 ${38 * u}px Inter,sans-serif;white-space:nowrap`;
          st.pts.push({ e, t0: t0 + 0.14 * k + 0.1 });
        });
      });
      if (p.query) {
        const q = p.query, tx = x0 + q.x * W, ty = y0 + q.y * H, target = p.groups[q.group], gx = x0 + target.x * W, gy = y0 + target.y * H;
        const e = (st.q = el("div", "abs", root, L.esc(q.text))); L.pos(e, tx - 300 * u, ty - 44 * u, 600 * u); e.style.cssText += `;text-align:center;padding:${16 * u}px;border-radius:${14 * u}px;background:${AMBER};color:#0f0f10;font:900 ${42 * u}px Inter,sans-serif`;
        st.ql = L.svg("line", { x1: tx, y1: ty, x2: gx, y2: gy, stroke: AMBER, "stroke-width": 7 * u, filter: "url(#fv-bloom)", "stroke-linecap": "round" }, svg);
        st.qt = L.wordTime(c, q.word || "") ?? c.dur * 0.72;
      }
      return st;
    },
    update(st, t, c) {
      headingAt(st.head, t + 0.4);
      for (const s of st.pts) { if (s.halo) s.halo.style.opacity = 0.45 + 0.55 * eo(seg(t, s.t0, s.t0 + 0.4)); else rise(s.e, t, s.t0, 0.35, 10 * c.u, 0.4); }
      if (st.q) { rise(st.q, t, st.qt, 0.45, 18 * c.u); st.ql.style.opacity = eo(seg(t, st.qt + 0.3, st.qt + 0.7)); }
    },
    cues: (c) => { const p = c.p; const o = (p.groups || []).map((g, k, a) => ({ lt: when(c, g, k, a.length, 0.2, c.dur * 0.55), type: "swish", lvl: 2 })); if (p.query) o.push({ lt: L.wordTime(c, p.query.word || "") ?? c.dur * 0.72, type: "zap", lvl: 3 }); return o; },
  };
})();
