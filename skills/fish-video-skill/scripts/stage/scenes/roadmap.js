/* roadmap + pile: long-format explainer scenes.

   roadmap  a serpentine map of stops. The camera flies stop to stop and lands on spoken words,
            and it never looks past the map, so a frame edge is never bare background.
     nodes        [{tag, label, src | glyph}]
     visits       [{i, word | t}]   arrive at stop i on a spoken word, or at t seconds
     open_wide    seconds: open on the whole map, then push in to the current stop
     pull_word | pull_at, pull_dur, reveal_all   pull back to the whole map; reveal_all lights it all
     kicker, cta, cta_word, cols (4), zoom (1.42), wide_zoom (.68), move (.8)

   pile     real websites land big in the centre, one by one, then settle into a pile; a line lands last.
     cards        [{src, url, x, y, w, rot, word | at}]   (x, y, w are fractions of the frame)
     chips        ["tag", ...], chip_every (.3)
     title, title_word, title_cue (swell), title_size (150), hold_last */
(function () {
  "use strict";
  const S = (window.SCENES = window.SCENES || {});
  const { el, seg, eo, clamp, C } = L;
  const glow = (a) => L.hexA(C.accent, a);
  const accent = (txt) => L.esc(String(txt)).replace(/\*([^*]+)\*/g, `<span style="color:${C.accent}">$1</span>`).replace(/\\n|\n/g, "<br>");

  function ground(root, c) {
    const g = el("div", "abs", root); L.pos(g, 0, 0, c.W, c.H);
    const s = 56 * c.u;
    g.style.cssText += `;background-color:${C.bg};background-image:radial-gradient(ellipse at 50% 40%,${glow(0.13)},transparent 62%),linear-gradient(${L.hexA(C.ink, 0.055)} 1px,transparent 1px),linear-gradient(90deg,${L.hexA(C.ink, 0.055)} 1px,transparent 1px);background-size:100% 100%,${s}px ${s}px,${s}px ${s}px`;
    return g;
  }
  function browser(parent, src, url, w, h, u) {
    const b = el("div", "abs", parent); L.pos(b, 0, 0, w, h); b.dataset.nolint = "";
    b.style.cssText += `;border-radius:${14 * u}px;overflow:hidden;background:#17181b;box-shadow:0 ${26 * u}px ${70 * u}px rgba(0,0,0,.7),0 0 0 ${2 * u}px rgba(255,255,255,.18)`;
    const bar = el("div", "abs", b), bh = 44 * u; L.pos(bar, 0, 0, w, bh);
    bar.style.cssText += `;background:#26282d;display:flex;align-items:center;gap:${9 * u}px;padding-left:${16 * u}px;box-sizing:border-box`;
    ["#ff5f57", "#febc2e", "#28c840"].forEach((k) => { const d = el("div", "", bar); d.style.cssText = `width:${13 * u}px;height:${13 * u}px;border-radius:50%;background:${k};flex:none`; });
    const a = el("div", "", bar, L.esc(url || "")); a.style.cssText = `margin-left:${14 * u}px;padding:${5 * u}px ${18 * u}px;border-radius:${14 * u}px;background:#15161a;color:#c9cbd1;font:500 ${18 * u}px var(--display);white-space:nowrap`;
    const box = el("div", "abs", b); L.pos(box, 0, bh, w, h - bh); box.style.overflow = "hidden";
    const img = el("img", "", box); img.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;object-position:top";
    L.setImg(img, L.projUrl(src));
    return b;
  }
  const when = (c, it, k, n, t0, t1) => {
    const w = it && it.word ? L.wordTime(c, it.word) : null;
    if (w != null) return w;
    if (it && it.at != null) return it.at;
    return t0 + (n > 1 ? (k * (t1 - t0)) / (n - 1) : 0);
  };
  const titleTime = (c) => L.wordTime(c, c.p.title_word || "") ?? c.dur - 1.4;
  const pileEnd = (c) => (c.p.title ? Math.max(0.3, titleTime(c) - 0.5) : c.dur - 1);

  S.pile = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { cards: [], chips: [] };
      ground(root, c);
      (p.chips || []).forEach((tx, i) => {
        const d = el("div", "abs", root, L.esc(tx)), q = L.rng(i + 11);
        L.pos(d, c.safe.x + (c.safe.w - 300 * u) * ((i * 0.618 + 0.07) % 1), c.safe.y + (c.safe.h - 80 * u) * ((i * 0.381 + 0.11) % 1));
        d.style.cssText += `;padding:${10 * u}px ${22 * u}px;border-radius:${40 * u}px;border:${2 * u}px solid ${glow(0.65)};color:${C.accent};background:${L.hexA(C.bg, 0.86)};font:700 ${30 * u}px var(--display);white-space:nowrap`;
        st.chips.push({ d, t0: 0.15 + i * (p.chip_every || 0.3), rot: (q() - 0.5) * 12 });
      });
      const n = (p.cards || []).length;
      (p.cards || []).forEach((it, k) => {
        const w = (it.w || 0.5) * c.W, h = w * 0.66, wrap = el("div", "abs", root);
        L.pos(wrap, it.x * c.W - w / 2, it.y * c.H - h / 2, w, h);
        browser(wrap, it.src, it.url, w, h, u);
        st.cards.push({ wrap, it, w, t0: k === 0 ? -0.6 : when(c, it, k, n, 0, pileEnd(c)) });
      });
      st.cards.forEach((s, k) => { const nx = st.cards[k + 1]; s.settle = nx ? nx.t0 : s.t0 + 0.42 + (p.hold_last || 0); s.dx = (0.5 - s.it.x) * c.W; s.dy = (0.5 - s.it.y) * c.H; s.big = (0.74 * c.W) / s.w; });
      st.chips.forEach((x) => root.appendChild(x.d));
      st.tt = p.title ? titleTime(c) : 1e9;
      if (p.title) {
        const sc = (st.scrim = el("div", "abs", root)); L.pos(sc, 0, 0, c.W, c.H); sc.style.background = "rgba(8,8,9,.74)";
        const T = (st.T = el("div", "abs", root, `<span>${accent(p.title)}</span>`));
        L.pos(T, c.safe.x + 80 * u, c.H * 0.27, c.safe.w - 160 * u, c.H * 0.46);
        T.style.cssText += `;display:flex;align-items:center;justify-content:center;text-align:center;color:#fff;font:900 ${(p.title_size || 150) * u}px/1.02 var(--display);letter-spacing:-.03em;text-shadow:0 ${8 * u}px ${40 * u}px #000`;
      }
      return st;
    },
    update(st, t, c) {
      for (const s of st.chips) { s.d.style.opacity = eo(seg(t, s.t0, s.t0 + 0.1)); s.d.style.transform = `rotate(${s.rot}deg) scale(${L.back(seg(t, s.t0, s.t0 + 0.28), 1.8)})`; }
      for (const s of st.cards) {
        const a = eo(seg(t, s.t0, s.t0 + 0.25)), m = eo(seg(t, s.settle, s.settle + 0.3));
        s.wrap.style.opacity = a;
        s.wrap.style.transform = `translate(${s.dx * (1 - m)}px,${s.dy * (1 - m) + (t - s.t0) * 3 * c.u}px) rotate(${(s.it.rot || 0) * m}deg) scale(${(s.big + (1 - s.big) * m) * (1.15 - 0.15 * a)})`;
      }
      if (st.T) { const q = eo(seg(t, st.tt, st.tt + 0.3)); st.scrim.style.opacity = q; st.T.style.opacity = q; st.T.style.transform = `scale(${1.05 - 0.05 * q + Math.max(0, t - st.tt) * 0.004})`; }
    },
    cues: (c) => {
      const out = [], n = (c.p.cards || []).length;
      (c.p.cards || []).forEach((it, k) => { if (k) out.push({ lt: when(c, it, k, n, 0, pileEnd(c)), type: "thump", lvl: 2 }); });
      if (c.p.title) out.push({ lt: titleTime(c), type: c.p.title_cue || "swell", lvl: 3 });
      return out;
    },
  };

  const visitTime = (c, v) => (v.word ? L.wordTime(c, v.word) ?? v.t ?? 0 : v.t || 0);
  const pullTime = (c) => (c.p.pull_word ? L.wordTime(c, c.p.pull_word) : c.p.pull_at);

  S.roadmap = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { nodes: [] };
      ground(root, c);
      const world = (st.world = el("div", "abs", root)); world.dataset.nolint = ""; L.pos(world, 0, 0, c.W, c.H); world.style.transformOrigin = "0 0";
      const NW = (st.NW = 470 * u), NH = (st.NH = 350 * u), DX = 610 * u, DY = 500 * u, cols = p.cols || 4;
      st.pts = (p.nodes || []).map((_, i) => { const row = Math.floor(i / cols), col = row % 2 ? cols - 1 - (i % cols) : i % cols; return { X: col * DX, Y: row * DY }; });
      const svg = L.svg("svg", { width: 10, height: 10 }, world); svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible";
      const pts = st.pts.map((q) => `${q.X},${q.Y}`).join(" ");
      L.svg("polyline", { points: pts, fill: "none", stroke: L.hexA(C.ink, 0.2), "stroke-width": 5 * u, "stroke-dasharray": `${10 * u} ${14 * u}` }, svg);
      st.line = L.svg("polyline", { points: pts, fill: "none", stroke: C.accent, "stroke-width": 9 * u, "stroke-linecap": "round" }, svg);
      /* a CSS shadow, not the SVG bloom filter: a one-row map is a flat line, and an SVG filter hides a zero-height box */
      st.line.style.filter = `drop-shadow(0 0 ${7 * u}px ${C.accent}) drop-shadow(0 0 ${18 * u}px ${glow(0.55)})`;
      st.seg = st.pts.slice(1).map((q, i) => Math.hypot(q.X - st.pts[i].X, q.Y - st.pts[i].Y));
      st.len = st.seg.reduce((a, b) => a + b, 0);
      st.line.setAttribute("stroke-dasharray", `${st.len} ${st.len}`);
      st.dot = L.svg("circle", { r: 16 * u, fill: "#fff", filter: "url(#fv-bloom)" }, svg);
      (p.nodes || []).forEach((n, i) => {
        const q = st.pts[i], d = el("div", "abs", world); L.pos(d, q.X - NW / 2, q.Y - NH / 2, NW, NH);
        d.style.cssText += `;box-sizing:border-box;border-radius:${22 * u}px;background:${C.surface};border:${3 * u}px solid ${L.hexA(C.ink, 0.22)};overflow:hidden`;
        const im = el("div", "abs", d); L.pos(im, 0, 0, NW, NH * 0.56); im.style.overflow = "hidden";
        if (n.src) { const img = el("img", "", im); img.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;object-position:top"; L.setImg(img, L.projUrl(n.src)); }
        else { const ic = el("div", "abs", im, L.esc(n.glyph || "")); L.pos(ic, 0, 0, NW, NH * 0.56); ic.style.cssText += `;display:flex;align-items:center;justify-content:center;color:${C.accent};font:800 ${58 * u}px 'JetBrains Mono',monospace`; }
        const tag = el("div", "abs", d, L.esc(n.tag || "")); L.pos(tag, 22 * u, NH * 0.6); tag.style.cssText += `;color:${C.accent};font:800 ${25 * u}px var(--display);letter-spacing:.09em`;
        const lb = el("div", "abs", d, L.esc(n.label || "")); L.pos(lb, 22 * u, NH * 0.71, NW - 44 * u); lb.style.cssText += `;color:${C.ink};font:800 ${44 * u}px/1.05 var(--display);letter-spacing:-.015em`;
        st.nodes.push({ d, i });
      });
      if (p.kicker) { const k = (st.k = el("div", "abs", root, L.esc(p.kicker))); L.pos(k, c.safe.x, c.safe.y); k.style.cssText += `;padding:${12 * u}px ${24 * u}px;border-radius:${12 * u}px;background:${C.accent};color:${C.bg};font:900 ${34 * u}px var(--display);letter-spacing:.02em;white-space:nowrap`; }
      if (p.cta) { const a = (st.cta = el("div", "abs", root, `<span>${accent(p.cta)}</span>`)); L.pos(a, c.safe.x, c.safe.y + c.safe.h - 90 * u, c.safe.w, 90 * u); a.style.cssText += `;display:flex;align-items:center;justify-content:center;color:${C.ink};font:900 ${60 * u}px var(--display);letter-spacing:-.02em`; }
      st.V = (p.visits || [{ i: 0, t: 0 }]).map((v) => ({ i: v.i, t: visitTime(c, v) }));
      st.pull = pullTime(c);
      return st;
    },
    update(st, t, c) {
      const p = c.p, u = c.u, V = st.V;
      let i = 0; while (i < V.length - 1 && t >= V[i + 1].t) i++;
      const a = V[i], b = V[i + 1] || a, x = b === a ? 1 : L.expo(seg(t, Math.max(a.t, b.t - (p.move || 0.8)), b.t));
      const f = a.i + (b.i - a.i) * x;
      const pullOut = st.pull != null ? eo(seg(t, st.pull, st.pull + (p.pull_dur || 1))) : 0;
      const po = Math.max(pullOut, p.open_wide ? 1 - eo(seg(t, 0.15, p.open_wide)) : 0);
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
      const hw = c.W / 2 / zoom, hh = c.H / 2 / zoom, mX = st.NW / 2 + 40 * u, mY = st.NH / 2 + 40 * u;
      const hold = (v, lo, hi, m) => (lo > hi ? m : clamp(v, lo, hi));
      const cX = hold(X, x0 - mX + hw, x1 + mX - hw, midX), cY = hold(Y, y0 - mY + hh, y1 + mY - hh, midY);
      const cx = cX + (midX - cX) * po, cy = cY + (midY - cY) * po;
      st.world.style.transform = `translate(${c.W / 2 - cx * zoom}px,${c.H / 2 - cy * zoom}px) scale(${zoom})`;
      for (const n of st.nodes) {
        const lit = f >= n.i - 0.06 || allOn * (st.nodes.length - 1) >= n.i, here = Math.abs(f - n.i) < 0.5 && !allOn;
        n.d.style.borderColor = lit ? C.accent : L.hexA(C.ink, 0.22);
        n.d.style.boxShadow = lit ? `0 0 ${(here ? 70 : 34) * u}px ${glow(here ? 0.6 : 0.3)}` : "none";
        n.d.style.opacity = lit || po > 0.3 ? 1 : 0.78;
      }
      if (st.k) st.k.style.opacity = eo(seg(po, 0.35, 0.75));
      if (st.cta) { const k = p.cta_word ? L.wordTime(c, p.cta_word) ?? 0.5 : st.pull != null ? st.pull + 0.6 : 0.5, q = eo(seg(t, k, k + 0.5)); st.cta.style.opacity = q; st.cta.style.transform = `translateY(${(1 - q) * 26}px)`; }
    },
    cues: (c) => {
      const out = [{ lt: 0, type: "swish", lvl: 2 }];
      (c.p.visits || []).slice(1).forEach((v) => { const tt = visitTime(c, v); out.push({ lt: Math.max(0, tt - 0.5), type: "whoosh", lvl: 2 }); out.push({ lt: tt, type: "zap", lvl: 2 }); });
      const pull = pullTime(c);
      if (pull != null) { out.push({ lt: pull, type: "whoosh", lvl: 2 }); out.push({ lt: pull + (c.p.pull_dur || 1), type: "chime", lvl: 3 }); }
      return out;
    },
  };
})();
