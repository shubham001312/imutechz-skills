/* Onoda series scenes (Part 1 and Part 2 share this file). Every update is a pure function of t.
   One photo ground with a slow push, a drawing accent line, a kicker, stacked lines, and one motif. */
(function () {
  "use strict";
  const S = (window.SCENES = window.SCENES || {});
  const { el, seg, eo, clamp } = L;
  const AMBER = "#f2b722";
  const INK = "#f5f5f5";
  const MUTED = "#c4c7cf";
  const mark = (txt) => L.esc(String(txt)).replace(/\*([^*]+)\*/g, `<span style="color:${AMBER}">$1</span>`).replace(/\\n|\n/g, "<br>");
  const when = (c, it, k) => {
    const w = it.word ? L.wordTime(c, it.word) : null;
    if (w != null) return Math.max(0, w - 0.12);
    return it.at != null ? it.at : 0.1 + k * 0.55;
  };

  S.onoda_card = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { c };
      const bg = el("div", "abs", root); L.pos(bg, 0, 0, c.W, c.H); bg.style.cssText += ";overflow:hidden;background:#050505";
      const img = el("img", "", bg);
      img.style.cssText = `position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;object-position:${p.pos || "50% 50%"};filter:saturate(.8) contrast(1.06) brightness(${p.bright || 0.62});transform-origin:${p.origin || "50% 50%"}`;
      L.setImg(img, L.projUrl(p.src));
      st.img = img;
      if (p.contain) {
        img.style.filter = "blur(26px) saturate(.7) brightness(.4)"; img.style.transform = "scale(1.2)";
        const w = c.safe.w, h = w / (p.ar || 1.327), y0 = c.safe.y + 120 * u;
        const card = el("div", "abs", root); L.pos(card, c.safe.x, y0, w, h);
        card.style.cssText += `;overflow:hidden;border-radius:${10 * u}px;box-shadow:0 ${24 * u}px ${70 * u}px rgba(0,0,0,.8),0 0 0 ${3 * u}px ${AMBER}`;
        const im2 = el("img", "", card);
        im2.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;filter:grayscale(.15) contrast(1.05);transform-origin:70% 55%";
        L.setImg(im2, L.projUrl(p.src)); st.img2 = im2; st.card = card;
      }
      const sc = el("div", "abs", root); L.pos(sc, 0, 0, c.W, c.H);
      sc.style.cssText += ";background:linear-gradient(180deg,rgba(5,5,5,.55) 0%,rgba(5,5,5,.05) 28%,rgba(5,5,5,.15) 52%,rgba(5,5,5,.82) 100%)";
      const fx = el("div", "abs", root); L.pos(fx, 0, 0, c.W, c.H); fx.style.overflow = "hidden"; st.fx = fx;
      // kicker chip
      if (p.kicker) {
        const k = el("div", "abs", root, L.esc(p.kicker));
        L.pos(k, c.safe.x, c.safe.y + 6 * u);
        k.style.cssText += `;padding:${10 * u}px ${20 * u}px;border-radius:${8 * u}px;background:${AMBER};color:#111;font:800 ${28 * u}px/1 Inter,sans-serif;letter-spacing:${3 * u}px;text-transform:uppercase`;
        st.k = k;
      }
      // accent line that draws across
      const ln = el("div", "abs", root); L.pos(ln, c.safe.x, c.safe.y + 84 * u, c.safe.w, 4 * u);
      ln.style.cssText += `;background:${AMBER};transform-origin:0 50%;box-shadow:0 0 ${18 * u}px ${AMBER}`;
      st.ln = ln;
      // lines
      const lines = p.lines || [];
      st.lines = [];
      const blockH = c.safe.h * (p.block || 0.42);
      const top = c.safe.y + c.safe.h - blockH - (p.lift != null ? p.lift : 140) * u;
      const per = blockH / Math.max(1, lines.length);
      lines.forEach((it, k) => {
        const o = typeof it === "string" ? { text: it } : it;
        const d = el("div", "abs", root, `<div style="width:100%">${mark(o.text)}</div>`);
        L.pos(d, c.safe.x, top + k * per, c.safe.w, per);
        d.style.cssText += `;display:flex;align-items:center;justify-content:${p.align === "left" ? "flex-start" : "center"};text-align:${p.align === "left" ? "left" : "center"};color:${o.dim ? MUTED : INK};font:900 ${(o.size || 120) * u}px/1 Inter,sans-serif;text-transform:uppercase;white-space:nowrap;text-shadow:0 ${4 * u}px ${28 * u}px rgba(0,0,0,.85)`;
        L.fit(d, (o.size || 120) * u, 40 * u, c.safe.w, per);
        st.lines.push({ d, t0: when(c, o, k) });
      });
      // motifs
      const m = p.motif || "none";
      st.m = m;
      if (m === "leaflets") {
        st.leaf = [];
        const r = L.rng(7);
        for (let i = 0; i < 16; i++) {
          const w = (60 + r() * 50) * u, h = w * 1.3;
          const d = el("div", "abs", fx); L.pos(d, 0, 0, w, h);
          d.style.cssText += `;background:linear-gradient(#f1ede2,#d9d3c3);border-radius:${3 * u}px;box-shadow:0 ${6 * u}px ${18 * u}px rgba(0,0,0,.5);opacity:.92`;
          d.innerHTML = `<div style="margin:${w * 0.16}px;height:${w * 0.05}px;background:#7a7566;opacity:.7"></div><div style="margin:${w * 0.1}px ${w * 0.16}px;height:${w * 0.05}px;background:#7a7566;opacity:.5"></div><div style="margin:${w * 0.1}px ${w * 0.16}px;height:${w * 0.05}px;background:#7a7566;opacity:.5"></div>`;
          st.leaf.push({ d, x: r(), ph: r(), sp: 0.5 + r() * 0.6, sw: 30 + r() * 70, rot: r() * 360, rs: (r() - 0.5) * 220 });
        }
      } else if (m === "rings") {
        st.ringEls = [];
        for (let i = 0; i < 4; i++) {
          const d = el("div", "abs", fx);
          d.style.cssText += `;border:${5 * u}px solid ${AMBER};border-radius:50%;box-shadow:0 0 ${24 * u}px rgba(242,183,34,.55)`;
          st.ringEls.push(d);
        }
        st.rx = (p.rx != null ? p.rx : 0.5) * c.W; st.ry = (p.ry != null ? p.ry : 0.34) * c.H;
        const dot = el("div", "abs", fx); const ds = 34 * u; L.pos(dot, st.rx - ds / 2, st.ry - ds / 2, ds, ds);
        dot.style.cssText += `;border-radius:50%;background:${AMBER};box-shadow:0 0 ${30 * u}px ${AMBER}`;
        st.dot = dot;
      } else if (m === "route") {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("width", c.W); svg.setAttribute("height", c.H); svg.style.cssText = "position:absolute;left:0;top:0";
        fx.appendChild(svg);
        const x0 = c.safe.x + 40 * u, y0 = c.safe.y + c.safe.h * 0.34, x1 = c.safe.x + c.safe.w - 60 * u, y1 = c.safe.y + c.safe.h * 0.2;
        const cx = (x0 + x1) / 2, cy = c.safe.y + c.safe.h * 0.02;
        st.rt = { x0, y0, x1, y1, cx, cy };
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", `M${x0},${y0} Q${cx},${cy} ${x1},${y1}`);
        path.setAttribute("fill", "none"); path.setAttribute("stroke", AMBER); path.setAttribute("stroke-width", 5 * u);
        path.setAttribute("stroke-dasharray", `${16 * u} ${14 * u}`); path.setAttribute("stroke-linecap", "round");
        svg.appendChild(path);
        const mk = (x, y, txt, left) => {
          const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
          dot.setAttribute("cx", x); dot.setAttribute("cy", y); dot.setAttribute("r", 14 * u); dot.setAttribute("fill", AMBER);
          svg.appendChild(dot);
          const t = el("div", "abs", fx, txt); L.pos(t, left ? x - 10 * u : x - 210 * u, y + 24 * u, 220 * u);
          t.style.cssText += `;color:${INK};font:800 ${30 * u}px/1 Inter,sans-serif;letter-spacing:${3 * u}px;text-align:${left ? "left" : "right"};text-shadow:0 2px 12px #000`;
        };
        mk(x0, y0, p.from || "JAPAN", true); mk(x1, y1, p.to || "LUBANG", false);
        const plane = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
        plane.setAttribute("points", `${28 * u},0 ${-18 * u},${-18 * u} ${-8 * u},0 ${-18 * u},${18 * u}`);
        plane.setAttribute("fill", INK);
        svg.appendChild(plane); st.plane = plane;
      } else if (m === "stamp") {
        const s = el("div", "abs", root, L.esc(p.stamp || "PART 2"));
        L.pos(s, c.safe.x + c.safe.w * 0.08, c.safe.y + c.safe.h * 0.2, c.safe.w * 0.84, c.safe.h * 0.2);
        s.style.cssText += `;display:flex;align-items:center;justify-content:center;color:${AMBER};font:900 ${200 * u}px/1 Inter,sans-serif;letter-spacing:${4 * u}px;border:${10 * u}px solid ${AMBER};border-radius:${18 * u}px;box-sizing:border-box;background:rgba(5,5,5,.55);box-shadow:0 0 ${50 * u}px rgba(242,183,34,.45)`;
        L.fit(s, 200 * u, 60 * u, c.safe.w * 0.84 - 60 * u, c.safe.h * 0.2 - 40 * u);
        st.stamp = s;
        const w = p.stamp_word ? L.wordTime(c, p.stamp_word) : null; st.sT = w != null ? Math.max(0, w - 0.1) : 0;
      } else if (m === "date") {
        const s = el("div", "abs", root, L.esc(p.date || ""));
        L.pos(s, c.safe.x, c.safe.y + c.safe.h * 0.12, c.safe.w, c.safe.h * 0.22);
        s.style.cssText += `;display:flex;align-items:center;justify-content:center;color:transparent;-webkit-text-stroke:${4 * u}px ${AMBER};font:900 ${230 * u}px/1 Inter,sans-serif;letter-spacing:${6 * u}px;text-shadow:0 0 ${40 * u}px rgba(242,183,34,.35)`;
        L.fit(s, 230 * u, 80 * u, c.safe.w, c.safe.h * 0.22);
        st.date = s;
      }
      return st;
    },
    update(st, t, c) {
      const u = c.u, p = c.p;
      // push-in
      const k = clamp(t / c.dur, 0, 1);
      const z0 = p.z0 != null ? p.z0 : 1.04, z1 = p.z1 != null ? p.z1 : 1.18;
      if (st.img2) { st.img2.style.transform = `scale(${1.02 + 0.16 * k})`; }
      else st.img.style.transform = `scale(${z0 + (z1 - z0) * k}) translate(${(p.dx || 0) * (k - 0.5) * 40}px,0)`;
      st.ln.style.transform = `scaleX(${eo(seg(t, p.up0 ? -0.8 : 0, p.up0 ? 0.4 : 0.6))})`;
      if (st.k) { const q = eo(seg(t, p.up0 ? -0.5 : 0, p.up0 ? -0.1 : 0.35)); st.k.style.opacity = 0.0 + q; st.k.style.transform = `translateY(${(1 - q) * -14}px)`; }
      // lines are up (partly) from frame 0; each lands on its time
      st.lines.forEach((o) => {
        const q = eo(seg(t, o.t0, o.t0 + 0.38));
        o.d.style.opacity = 0.0 + q;
        o.d.style.transform = `translateY(${(1 - q) * 34 * u}px) scale(${0.94 + 0.06 * q})`;
      });
      if (st.m === "leaflets") {
        const H = c.H + 300 * u;
        st.leaf.forEach((l) => {
          const ph = (t * 0.22 * l.sp + l.ph) % 1;
          const y = -150 * u + ph * H;
          const x = l.x * c.W + Math.sin((t * 1.3 * l.sp) + l.ph * 9) * l.sw * u;
          l.d.style.transform = `translate(${x}px,${y}px) rotate(${l.rot + l.rs * t}deg) rotateX(${Math.sin(t * 2 + l.ph * 6) * 50}deg)`;
        });
      } else if (st.m === "rings") {
        st.ringEls.forEach((d, i) => {
          const ph = ((t * 0.8 + i / 4) % 1);
          const r = (40 + ph * 460) * u;
          L.pos(d, st.rx - r, st.ry - r, r * 2, r * 2);
          d.style.opacity = (1 - ph) * 0.9;
        });
        st.dot.style.transform = `scale(${1 + 0.15 * Math.sin(t * 9)})`;
      } else if (st.m === "route") {
        const { x0, y0, x1, y1, cx, cy } = st.rt;
        const s = clamp(t / Math.max(0.5, c.dur * 0.85), 0, 1), a = eo(s);
        const bx = (1 - a) * (1 - a) * x0 + 2 * (1 - a) * a * cx + a * a * x1;
        const by = (1 - a) * (1 - a) * y0 + 2 * (1 - a) * a * cy + a * a * y1;
        const tx = 2 * (1 - a) * (cx - x0) + 2 * a * (x1 - cx), ty = 2 * (1 - a) * (cy - y0) + 2 * a * (y1 - cy);
        st.plane.setAttribute("transform", `translate(${bx},${by}) rotate(${Math.atan2(ty, tx) * 180 / Math.PI}) scale(1.3)`);
      } else if (st.m === "stamp") {
        const q = eo(seg(t, st.sT, st.sT + 0.35));
        st.stamp.style.opacity = q;
        st.stamp.style.transform = `scale(${1.25 - 0.25 * q}) rotate(${-4 * q}deg)`;
      } else if (st.m === "date") {
        const q = eo(seg(t, 0, 0.4));
        st.date.style.opacity = q; st.date.style.transform = `scale(${1.1 - 0.1 * q})`;
      }
      L.H && L.H.outAll && L.H.outAll([], t, c);
    },
    cues: (c) => {
      const out = [{ lt: 0.05, type: "tick" }];
      return out;
    },
  };

  /* ---------- v2: image-led scene. Slides crossfade; every slide pushes slowly; text is a small overlay. ---------- */
  S.onoda_img = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { slides: [], lines: [] };
      const base = el("div", "abs", root); L.pos(base, 0, 0, c.W, c.H); base.style.background = "#050505";
      const sl = p.slides || [];
      sl.forEach((s, i) => {
        const w = el("div", "abs", root); L.pos(w, 0, 0, c.W, c.H); w.style.overflow = "hidden";
        const mode = s.mode || "cover";
        const o = { w, s, mode };
        const bgi = el("img", "", w);
        bgi.style.cssText = `position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;object-position:${s.pos || "50% 50%"};transform-origin:${s.origin || "50% 50%"}`;
        L.setImg(bgi, L.projUrl(s.src)); o.bg = bgi;
        if (mode === "card") {
          bgi.style.filter = "blur(30px) brightness(.5) saturate(.8)"; bgi.style.transform = "scale(1.25)";
          const ar = s.ar || 1;
          let cw = c.safe.w * (s.w || 0.8), ch = cw / ar;
          const maxh = c.safe.h * 0.6; if (ch > maxh) { ch = maxh; cw = ch * ar; }
          const card = el("div", "abs", w); L.pos(card, c.W / 2 - cw / 2, c.safe.y + 150 * u, cw, ch);
          card.style.cssText += `;overflow:hidden;border-radius:${8 * u}px;box-shadow:0 ${24 * u}px ${70 * u}px rgba(0,0,0,.8),0 0 0 ${3 * u}px ${AMBER}`;
          const im = el("img", "", card);
          im.style.cssText = `position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;object-position:${s.pos || "50% 50%"};transform-origin:${s.origin || "50% 40%"};filter:contrast(1.04)`;
          L.setImg(im, L.projUrl(s.src)); o.im = im;
        } else {
          bgi.style.filter = `saturate(.9) contrast(1.05) brightness(${s.bright || 0.8})`;
        }
        if (s.label) {
          const lb = el("div", "abs", w, L.esc(s.label));
          L.pos(lb, c.safe.x, c.safe.y + 100 * u + (mode === "card" ? 0 : 0));
          lb.style.cssText += `;max-width:${c.safe.w}px;padding:${7 * u}px ${14 * u}px;border-radius:${6 * u}px;background:rgba(5,5,5,.72);color:#e9e9ea;font:700 ${28 * u}px/1.15 Inter,sans-serif;letter-spacing:${1.5 * u}px;text-transform:uppercase;border-left:${4 * u}px solid ${AMBER}`;
          o.lb = lb;
        }
        st.slides.push(o);
      });
      // bottom scrim + kicker + line + overlay text
      const scr = el("div", "abs", root); L.pos(scr, 0, 0, c.W, c.H);
      scr.style.cssText += ";background:linear-gradient(180deg,rgba(5,5,5,.5) 0%,rgba(5,5,5,0) 20%,rgba(5,5,5,0) 40%,rgba(5,5,5,.88) 100%)";
      if (p.kicker) {
        const k = el("div", "abs", root, L.esc(p.kicker)); L.pos(k, c.safe.x, c.safe.y + 6 * u);
        k.style.cssText += `;padding:${9 * u}px ${18 * u}px;border-radius:${8 * u}px;background:${AMBER};color:#111;font:800 ${28 * u}px/1 Inter,sans-serif;letter-spacing:${3 * u}px;text-transform:uppercase`;
      }
      const ln = el("div", "abs", root); L.pos(ln, c.safe.x, c.safe.y + 76 * u, c.safe.w, 4 * u);
      ln.style.cssText += `;background:${AMBER};box-shadow:0 0 ${14 * u}px ${AMBER}`;
      const lines = p.lines || [], blockH = c.safe.h * (p.block || 0.2), top = c.safe.y + c.safe.h - blockH - (p.lift != null ? p.lift : 140) * u, per = blockH / Math.max(1, lines.length);
      lines.forEach((it, k) => {
        const o = typeof it === "string" ? { text: it } : it;
        const d = el("div", "abs", root, `<div style="width:100%">${mark(o.text)}</div>`);
        L.pos(d, c.safe.x, top + k * per, c.safe.w, per);
        d.style.cssText += `;display:flex;align-items:center;justify-content:center;text-align:center;color:${o.dim ? MUTED : INK};font:900 ${(o.size || 84) * u}px/1 Inter,sans-serif;text-transform:uppercase;white-space:nowrap;text-shadow:0 ${3 * u}px ${22 * u}px rgba(0,0,0,.95)`;
        L.fit(d, (o.size || 84) * u, 36 * u, c.safe.w, per);
        st.lines.push({ d, t0: o.at != null ? o.at : (o.word ? Math.max(0, (L.wordTime(c, o.word) ?? 0) - 0.12) : 0.1 + k * 0.5) });
      });
      // slide start times
      st.t = sl.map((s, i) => (s.word ? Math.max(0, (L.wordTime(c, s.word) ?? 0) - 0.15) : (s.t != null ? s.t : 0)));
      st.t[0] = 0;
      if (p.motif === "leaflets") {
        const fx = el("div", "abs", root); L.pos(fx, 0, 0, c.W, c.H); fx.style.overflow = "hidden"; st.leaf = [];
        const r = L.rng(7);
        for (let i = 0; i < 9; i++) {
          const w = (46 + r() * 34) * u, h = w * 1.3, d = el("div", "abs", fx); L.pos(d, 0, 0, w, h);
          d.style.cssText += `;background:linear-gradient(#f1ede2,#d9d3c3);border-radius:${3 * u}px;box-shadow:0 ${5 * u}px ${14 * u}px rgba(0,0,0,.5);opacity:.85`;
          st.leaf.push({ d, x: r(), ph: r(), sp: 0.5 + r() * 0.6, sw: 30 + r() * 60, rot: r() * 360, rs: (r() - 0.5) * 200 });
        }
      }
      if (p.stamp) {
        const s = el("div", "abs", root, L.esc(p.stamp)); L.pos(s, c.safe.x + c.safe.w * 0.12, c.safe.y + c.safe.h * 0.63, c.safe.w * 0.76, c.safe.h * 0.1);
        s.style.cssText += `;display:flex;align-items:center;justify-content:center;color:${AMBER};font:900 ${110 * u}px/1 Inter,sans-serif;letter-spacing:${4 * u}px;border:${7 * u}px solid ${AMBER};border-radius:${14 * u}px;box-sizing:border-box;background:rgba(5,5,5,.62);box-shadow:0 0 ${40 * u}px rgba(242,183,34,.45)`;
        L.fit(s, 110 * u, 40 * u, c.safe.w * 0.76 - 40 * u, c.safe.h * 0.1 - 24 * u);
        st.stamp = s; st.sT = p.stamp_word ? Math.max(0, (L.wordTime(c, p.stamp_word) ?? 0) - 0.1) : 0;
      }
      return st;
    },
    update(st, t, c) {
      const u = c.u, X = 0.4;
      st.slides.forEach((o, i) => {
        const t0 = st.t[i], t1 = i + 1 < st.slides.length ? st.t[i + 1] : c.dur + 1;
        const vis = i === 0 ? 1 : eo(seg(t, t0 - 0.02, t0 + X));
        const gone = i + 1 < st.slides.length ? 0 : 0;
        o.w.style.opacity = vis; o.w.style.display = (t < t0 - 0.05 && i > 0) ? "none" : "block";
        const k = clamp((t - t0) / Math.max(1, (t1 - t0) + X), 0, 1), s = o.s;
        const z0 = s.z0 != null ? s.z0 : 1.04, z1 = s.z1 != null ? s.z1 : 1.16, z = z0 + (z1 - z0) * k;
        const dx = (s.dx || 0) * (k - 0.5) * c.W * 0.06, dy = (s.dy || 0) * (k - 0.5) * c.H * 0.04;
        if (o.im) { o.im.style.transform = `scale(${z}) translate(${dx}px,${dy}px)`; }
        else o.bg.style.transform = `scale(${z}) translate(${dx}px,${dy}px)`;
        if (o.lb) { const q = eo(seg(t, t0 + 0.1, t0 + 0.5)); o.lb.style.opacity = q; }
      });
      st.lines.forEach((o) => { const q = eo(seg(t, o.t0, o.t0 + 0.35)); o.d.style.opacity = q; o.d.style.transform = `translateY(${(1 - q) * 22 * u}px)`; });
      if (st.leaf) st.leaf.forEach((l) => {
        const ph = (t * 0.22 * l.sp + l.ph) % 1, y = -120 * u + ph * (c.H + 240 * u), x = l.x * c.W + Math.sin(t * 1.3 * l.sp + l.ph * 9) * l.sw * u;
        l.d.style.transform = `translate(${x}px,${y}px) rotate(${l.rot + l.rs * t}deg)`;
      });
      if (st.stamp) { const q = eo(seg(t, st.sT, st.sT + 0.35)); st.stamp.style.opacity = q; st.stamp.style.transform = `scale(${1.2 - 0.2 * q}) rotate(${-3 * q}deg)`; }
    },
    cues: (c) => [{ lt: 0.05, type: "tick" }],
  };
})();
