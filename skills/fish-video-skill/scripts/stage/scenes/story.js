/* story, statement, cards, flow, site: the image-led and word-synced scenes of the long and short benchmark videos,
   generalised. No text, colours or assets are baked in: colours come from the theme (L.C), type and layout from
   the theme tokens (L.T, config/themes.yaml), content from params.

   story      a full-frame real photo with a slow push-in or pan, a kicker, stacked lines that land on spoken words,
              and one optional motif. The picture leads; the text is small and sits low.
     src | srcs [{src, word|at}]   one photo, or a sequence that cross-fades on spoken words (image changes inside a scene)
     pos ("50% 50%"), bright (.62), pan (left|right|up|down, default none), z0 (1.04), z1 (1.18), contain (true: framed card on a blurred ground), ar
     label (archive photo | illustrative: required by `fishvideo gates` for photos of people or events; shown as a caption strip over the picture, at least the lint minimum size)
     kicker, lines [{text, word|at, size, dim}], block (.42 share of the safe height), lift, align (center|left)
     motif    none | date | stamp | route | rings | dust     (date, stamp, from, to, stamp_word, rx, ry)
   statement  big calm lines. Later lines are visible but dimmed from frame 0 and light up on their word.
     lines [string | {text, word|at, size}], size (92), src (optional photo ground, dimmed), floor (.35)
   cards      a grid of ideas; every card is on screen (dimmed) from frame 0, the newest is lit.
     items [{tag, t, d, word|at, src}], cols, kicker, title, t_size (54), d_size (36), max_h (420)
   flow       a pipeline of boxes joined by glowing arrows.
     nodes [{glyph, label, sub, src, word|at}], kicker, title, size (46), h (430)
   site       a real website screenshot in a browser frame, notes landing beside it.
     shots [{src, url, word|at}] | src, url ; notes [string | {text, word|at}], kicker, title
   bold       a flat colour ground, one big shape and huge words that spring in on spoken words (typographic Shorts).
     lines [{text, word|at, size, color (ink|accent|chip)}], shape (circle|burst|bar|none), g (ground colour, default theme bg), shape_color
   Reveals land on `word` (a spoken word), else `at` (seconds), else are spread evenly. Pure functions of t. */
(function () {
  "use strict";
  const S = (window.SCENES = window.SCENES || {});
  const { el, seg, eo, clamp, C } = L;
  const T = () => L.T;
  const onAcc = () => (L.isDark(C.accent) ? "#ffffff" : "#0b0b0c");
  const fnt = (w, px, extra = "") => `font:${w || T().weight} ${px}px/1.08 var(--display);letter-spacing:${T().track}em;${T().caps ? "text-transform:uppercase;" : ""}${extra}`;
  const mark = (txt) => L.esc(String(txt)).replace(/\*([^*]+)\*/g, `<span style="color:${C.accent}">$1</span>`).replace(/\\n|\n/g, "<br>");
  /* an accent that stays readable over a photo: lifted toward white until it holds 7:1 against the near-black scrim */
  const rgb = (h) => { const n = parseInt(String(h).replace("#", ""), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
  const relLum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const x = relLum(a), y = relLum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const photoAccent = () => {
    let c = rgb(C.accent);
    for (let i = 0; i < 16 && ratio(c, [11, 11, 13]) < 7; i++) c = c.map((v) => Math.round(v + (255 - v) * 0.14));
    return "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
  };
  const markP = (txt) => L.esc(String(txt)).replace(/\*([^*]+)\*/g, `<span style="color:${photoAccent()}">$1</span>`).replace(/\\n|\n/g, "<br>");
  const when = (c, it, k, n, t0 = 0.2, t1) => {
    const w = it && it.word ? L.wordTime(c, it.word) : null;
    if (w != null) return Math.max(0, w - 0.12);
    if (it && it.at != null) return it.at;
    const end = t1 != null ? t1 : Math.max(t0 + 0.5, c.dur * 0.72);
    return t0 + (n > 1 ? (k * (end - t0)) / (n - 1) : 0);
  };
  const rise = (e, t, t0, d = 0.45, dist = 26, floor = 0, c) => {
    const m = T(), p = eo(seg(t, t0, t0 + d / m.speed));
    e.style.opacity = floor + (1 - floor) * p;
    e.style.transform = `translateY(${(1 - p) * dist * m.rise}px)`;
  };
  function ground(root, c) {
    const g = el("div", "abs", root); L.pos(g, 0, 0, c.W, c.H);
    g.style.cssText += `;background:radial-gradient(ellipse at 50% 40%,${L.hexA(C.accent, 0.13)},transparent 62%),${L.hexA(C.bg, 0.0)}`;
    return g;
  }
  function kickerEl(parent, text, c, abs = true) {
    const u = c.u, k = T().kicker, e = el("div", abs ? "abs" : "", parent, L.esc(text));
    const base = `${fnt(900, 28 * u)};letter-spacing:.06em;white-space:nowrap;`;
    const st = {
      chip: `padding:${10 * u}px ${20 * u}px;border-radius:${Math.min(T().radius, 14) * u}px;background:${C.accent};color:${onAcc()};`,
      pill: `padding:${10 * u}px ${26 * u}px;border-radius:${60 * u}px;background:${C.accent};color:${onAcc()};`,
      bar: `padding:${8 * u}px ${20 * u}px;background:${C.accent};color:${onAcc()};border-left:${10 * u}px solid ${C.ink};`,
      tape: `padding:${8 * u}px ${22 * u}px;background:${L.hexA(C.ink, 0.92)};color:${C.bg};transform:rotate(-1.5deg);box-shadow:0 ${4 * u}px ${12 * u}px rgba(0,0,0,.4);`,
      underline: `padding:0 0 ${8 * u}px;color:${C.accent};border-bottom:${4 * u}px solid ${C.accent};`,
      bracket: `padding:${4 * u}px ${10 * u}px;color:${C.accent};border-left:${4 * u}px solid ${C.accent};border-right:${4 * u}px solid ${C.accent};`,
    }[k] || "";
    e.style.cssText += `;${base}${st}`;
    return e;
  }
  function cardStyle(e, c, hot) {
    const u = c.u, m = T(), r = m.radius * u, b = Math.max(1, m.border) * u;
    const sh = m.shadow === "hard" ? `${8 * u}px ${8 * u}px 0 ${L.hexA(C.ink, 0.85)}` : m.shadow === "glow" ? `0 0 ${hot ? 44 * u : 18 * u}px ${L.hexA(C.accent, hot ? 0.55 : 0.2)}` : m.shadow === "none" ? "none" : `0 ${18 * u}px ${44 * u}px rgba(0,0,0,.35)`;
    const fill = m.card === "glass" ? L.hexA(C.surface, 0.62) : m.card === "outline" ? "transparent" : m.card === "ticket" ? C.paper : C.surface;
    e.style.cssText += `;box-sizing:border-box;border-radius:${r}px;background:${fill};border:${m.card === "flat" ? 0 : b}px solid ${hot ? C.accent : L.hexA(C.ink, m.card === "sticker" ? 0.9 : 0.24)};box-shadow:${sh};${m.card === "glass" ? "backdrop-filter:blur(8px);" : ""}`;
    if (m.card === "flat") e.style.borderLeft = `${6 * u}px solid ${hot ? C.accent : L.hexA(C.ink, 0.3)}`;
  }
  function heading(root, c, p, top) {
    const u = c.u, st = {};
    if (p.kicker) { st.k = kickerEl(root, p.kicker, c); L.pos(st.k, c.safe.x, top); top += 76 * u; }
    if (p.title) {
      st.h = el("div", "abs", root, mark(p.title)); L.pos(st.h, c.safe.x, top, c.safe.w);
      st.h.style.cssText += `;color:${C.ink};${fnt(null, (p.title_size || 66) * u)}`; top += ((p.title_size || 66) * 1.2 + 16) * u;
    }
    st.bottom = top;
    return st;
  }
  const headingAt = (st, t) => { if (st.k) rise(st.k, t, 0, 0.4, 14); if (st.h) rise(st.h, t, 0.06, 0.5, 20); };
  const photo = (parent, src, c, css) => {
    const img = el("img", "", parent);
    img.style.cssText = `position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;${css || ""}`;
    L.setImg(img, L.projUrl(src));
    return img;
  };

  /* ------------------------------------------------------------ story */
  /* How a picture is shown: full-bleed only when it is sharp enough for the frame (cover scale up to 1.3); otherwise a framed card on a
     blurred ground, never enlarged past 2.2x. scripts/gates.py mirrors these numbers (story_fit). */
  L.storyFit = (nw, nh, W, H) => {
    if (!nw || !nh) return { mode: "bleed", scale: 1 };
    const cover = Math.max(W / nw, H / nh);
    return cover <= 1.3 ? { mode: "bleed", scale: cover } : { mode: "frame", scale: Math.min(2.2, cover) };
  };
  S.story = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { c, imgs: [] };
      const srcs = p.srcs && p.srcs.length ? p.srcs : [{ src: p.src }];
      const px = p._px || {};
      const fits = srcs.map((it) => L.storyFit((px[it.src] || [])[0], (px[it.src] || [])[1], c.W, c.H));
      const framed = p.fit === "frame" || p.contain || (p.fit !== "bleed" && fits.some((f) => f.mode === "frame"));
      const bg = el("div", "abs", root); L.pos(bg, 0, 0, c.W, c.H); bg.style.cssText += `;overflow:hidden;background:${framed ? "#101012" : C.bg}`;
      st.framed = false;
      srcs.forEach((it, k) => {
        const im = photo(bg, framed && (p._ground || {})[it.src] ? p._ground[it.src] : it.src, c, `object-position:${p.pos || "50% 50%"};` + (framed ? "filter:blur(28px) saturate(.8) brightness(.42);transform:scale(1.25)" : `filter:saturate(1.04) contrast(1.02) brightness(${p.bright || 1})`));
        st.imgs.push({ im, t0: k === 0 ? -1 : when(c, it, k, srcs.length, 0.3, c.dur * 0.7) });
      });
      /* text zone and the (small) caption strip that tells the viewer what the picture is */
      const lines = p.lines || [], left = (p.align || T().align) === "left";
      let blockH = c.safe.h * (p.block || 0.34), top = c.safe.y + c.safe.h - blockH - (p.lift || 0) * u, per = blockH / Math.max(1, lines.length);
      const capText = [p.label ? String(p.label).toUpperCase() : "", p.caption ? String(p.caption).toUpperCase() : ""].filter(Boolean).join(" · ");
      const capPx = Math.max(24 * u, (c.minPx || 22) + 2);     /* the label meets the same lint as every other text */
      if (framed) {
        /* ONE large panel (about 88% of the width, 50-58% of the height), cover-cropped, with a slow pan and push so the view changes over the beat.
           The words sit directly below it on the backdrop. A second panel exists only for a DIFFERENT picture file assigned to this beat: the same
           file is never shown twice. A portrait picture gets a tall panel and is not cropped (no cut-off heads). Upscale stays within 2.2x. */
        const nat = px[srcs[0].src] || [0, 0], ar = nat[0] ? nat[0] / nat[1] : p.ar || 1.33;
        const need = lines.reduce((a, it) => a + ((typeof it === "string" ? 100 : it.size || 100) * 1.3 * u), 0), gap = 26 * u;
        const second = srcs.length > 1 && srcs[1].src && srcs[1].src !== srcs[0].src ? srcs[1] : null;
        const portrait = ar < 1, cwMax = Math.min(0.88 * c.W, c.safe.w), y0 = c.safe.y + 120 * u;
        const room = c.safe.y + c.safe.h - y0 - gap - need - 8 * u;           /* the panel and the words below it end inside the safe area */
        let cw, hA;
        if (portrait) { hA = Math.min(c.H * 0.52, room); cw = Math.min(cwMax, hA * ar); hA = cw / ar; }
        else { cw = cwMax; hA = Math.min(c.H * 0.54, room); if (nat[1]) hA = Math.min(hA, Math.max(nat[1] * 2.2, cw / ar)); }
        const x0 = c.safe.x + (c.safe.w - cw) / 2;
        const mkCard = (x, y, w, h, src, dir, vertical) => {
          const cd = el("div", "abs", root); L.pos(cd, x, y, w, h); cd.dataset.block = "sharp"; cd.dataset.src = src;
          cd.style.cssText += `;overflow:hidden;border-radius:${T().radius * 0.4 * u}px;box-shadow:0 ${24 * u}px ${70 * u}px rgba(0,0,0,.7),0 0 0 ${3 * u}px ${C.accent};background:#000`;
          return { cd, im: photo(cd, src, c, "filter:none"), dir, vertical };
        };
        top = y0 + hA + gap; blockH = need; per = need / Math.max(1, lines.length);
        const par = (c.index || 0) % 2 ? -1 : 1;
        st.fcards = [mkCard(x0, y0, cw, hA, srcs[0].src, par, portrait)];
        const bTop = top + need + gap, hB = second ? Math.min(c.safe.y + c.safe.h - bTop, cw * 0.9) : 0;
        if (second && hB > cw * 0.25) st.fcards.push(mkCard(x0, bTop, cw, hB, second.src, -par, false));
        if (capText) { const cp = el("div", "abs", root, L.esc(capText)); L.pos(cp, x0, y0 - capPx * 1.9);
          cp.style.cssText += `;max-width:${cw}px;padding:${5 * u}px ${12 * u}px;background:rgba(8,8,10,.8);color:#f8f6f0;font:700 ${capPx}px/1.15 var(--sans);letter-spacing:.06em;box-sizing:border-box`; }
      } else if (capText) {
        const cp = el("div", "abs", root, L.esc(capText)); L.pos(cp, c.safe.x, c.safe.y + 100 * u);
        cp.style.cssText += `;max-width:${c.safe.w}px;padding:${5 * u}px ${12 * u}px;background:rgba(8,8,10,.7);color:#f8f6f0;font:700 ${capPx}px/1.15 var(--sans);letter-spacing:.06em;box-sizing:border-box`;
      }
      /* scrim: a soft top for the kicker and a bottom only where the words are (the picture stays bright and sharp) */
      const sc = el("div", "abs", root); L.pos(sc, 0, 0, c.W, c.H);
      const textTop = (top - c.safe.h * 0.08) / c.H, ss = T().scrim;
      sc.style.cssText += `;background:linear-gradient(180deg,${L.hexA("#08080a", ss * 0.7)} 0%,${L.hexA("#08080a", 0)} 16%,${L.hexA("#08080a", 0)} ${(textTop * 100).toFixed(1)}%,${L.hexA("#08080a", framed ? 0.3 : 0.62)} 100%)`;
      const fx = (st.fx = el("div", "abs", root)); L.pos(fx, 0, 0, c.W, c.H); fx.style.overflow = "hidden";
      if (p.kicker) { st.k = kickerEl(root, p.kicker, c); L.pos(st.k, c.safe.x, c.safe.y + 6 * u); }
      const ln = (st.ln = el("div", "abs", root)); L.pos(ln, c.safe.x, c.safe.y + 84 * u, c.safe.w, 4 * u);
      ln.style.cssText += `;background:${C.accent};transform-origin:0 50%;box-shadow:0 0 ${18 * u}px ${C.accent}`;
      st.lines = lines.map((it, k) => {
        const o = typeof it === "string" ? { text: it } : it;
        const d = el("div", "abs", root, `<span class="fv-plate" style="background:rgba(8,8,10,.84);padding:.08em .34em .1em;border-radius:.18em;box-decoration-break:clone;-webkit-box-decoration-break:clone">${markP(o.text)}</span>`);
        L.pos(d, c.safe.x, top + k * per, c.safe.w, per);
        d.style.cssText += `;display:flex;align-items:center;justify-content:${left ? "flex-start" : "center"};text-align:${left ? "left" : "center"};color:${o.dim ? "#d3d0c8" : "#f8f6f0"};${fnt(null, (o.size || 100) * u)};line-height:1.2`;
        L.fit(d, (o.size || 100) * u, 40 * u, c.safe.w, per);
        return { d, t0: when(c, o, k, lines.length, 0.1, c.dur * 0.7) };
      });
      const m = (st.m = p.motif || "none");
      const svgNS = "http://www.w3.org/2000/svg";
      if (m === "date" || m === "stamp") {
        const txt = m === "date" ? p.date || "" : p.stamp || "";
        const e = (st[m] = el("div", "abs", root, L.esc(txt)));
        const box = m === "date" ? [c.safe.x, c.safe.y + c.safe.h * 0.12, c.safe.w, c.safe.h * 0.22] : [c.safe.x + c.safe.w * 0.08, c.safe.y + c.safe.h * 0.2, c.safe.w * 0.84, c.safe.h * 0.2];
        L.pos(e, ...box);
        e.style.cssText += m === "date"
          ? `;display:flex;align-items:center;justify-content:center;color:transparent;-webkit-text-stroke:${4 * u}px ${C.accent};${fnt(900, 230 * u)};text-shadow:0 0 ${40 * u}px ${L.hexA(C.accent, 0.35)}`
          : `;display:flex;align-items:center;justify-content:center;color:${C.accent};${fnt(900, 200 * u)};border:${10 * u}px solid ${C.accent};border-radius:${Math.min(T().radius, 18) * u}px;box-sizing:border-box;background:${L.hexA("#08080a", 0.5)}`;
        L.fit(e, (m === "date" ? 230 : 200) * u, 60 * u, box[2] - 40 * u, box[3] - 20 * u);
        const w = p.stamp_word ? L.wordTime(c, p.stamp_word) : null; st.sT = w != null ? Math.max(0, w - 0.1) : 0;
      } else if (m === "rings") {
        st.rings = [0, 1, 2, 3].map(() => { const d = el("div", "abs", fx); d.style.cssText += `;border:${5 * u}px solid ${C.accent};border-radius:50%;box-shadow:0 0 ${24 * u}px ${L.hexA(C.accent, 0.55)}`; return d; });
        st.rx = (p.rx != null ? p.rx : 0.5) * c.W; st.ry = (p.ry != null ? p.ry : 0.34) * c.H;
        const dot = (st.dot = el("div", "abs", fx)), ds = 34 * u; L.pos(dot, st.rx - ds / 2, st.ry - ds / 2, ds, ds);
        dot.style.cssText += `;border-radius:50%;background:${C.accent};box-shadow:0 0 ${30 * u}px ${C.accent}`;
      } else if (m === "dust") {
        const r = L.rng(7);
        st.dust = Array.from({ length: 28 }, () => { const d = el("div", "abs", fx), w = (4 + r() * 8) * u; L.pos(d, 0, 0, w, w); d.style.cssText += `;border-radius:50%;background:${L.hexA(C.ink, 0.5)}`; return { d, x: r(), ph: r(), sp: 0.4 + r() * 0.6, sw: 20 + r() * 60 }; });
      } else if (m === "route") {
        const svg = document.createElementNS(svgNS, "svg"); svg.setAttribute("width", c.W); svg.setAttribute("height", c.H); svg.style.cssText = "position:absolute;left:0;top:0"; fx.appendChild(svg);
        const x0 = c.safe.x + 40 * u, y0 = c.safe.y + c.safe.h * 0.34, x1 = c.safe.x + c.safe.w - 60 * u, y1 = c.safe.y + c.safe.h * 0.2, cx = (x0 + x1) / 2, cy = c.safe.y + c.safe.h * 0.02;
        st.rt = { x0, y0, x1, y1, cx, cy };
        const path = L.svg("path", { d: `M${x0},${y0} Q${cx},${cy} ${x1},${y1}`, fill: "none", stroke: C.accent, "stroke-width": 5 * u, "stroke-dasharray": `${16 * u} ${14 * u}`, "stroke-linecap": "round" }, svg);
        const mk = (x, y, txt, lf) => {
          L.svg("circle", { cx: x, cy: y, r: 14 * u, fill: C.accent }, svg);
          const t = el("div", "abs", fx, L.esc(txt)); L.pos(t, lf ? x - 10 * u : x - 210 * u, y + 24 * u, 220 * u);
          t.style.cssText += `;color:#f8f6f0;${fnt(800, 30 * u)};letter-spacing:.1em;text-align:${lf ? "left" : "right"};text-shadow:0 2px 12px #000`;
        };
        mk(x0, y0, p.from || "", true); mk(x1, y1, p.to || "", false);
        st.plane = L.svg("polygon", { points: `${28 * u},0 ${-18 * u},${-18 * u} ${-8 * u},0 ${-18 * u},${18 * u}`, fill: "#f8f6f0" }, svg);
      }
      return st;
    },
    update(st, t, c) {
      const u = c.u, p = c.p, m = T(), k = clamp(t / c.dur, 0, 1);
      const z0 = (p.z0 != null ? p.z0 : 1.04), z1 = z0 + ((p.z1 != null ? p.z1 : 1.18) - z0) * m.push;
      const pan = { left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] }[p.pan] || [0, 0];
      const tf = `scale(${z0 + (z1 - z0) * k}) translate(${pan[0] * (k - 0.5) * 60}px,${pan[1] * (k - 0.5) * 60}px)`;
      st.imgs.forEach((x, i) => {
        const a = i === 0 ? 1 : eo(seg(t, x.t0, x.t0 + 0.35));
        x.im.style.opacity = a;
        if (!st.fcards) x.im.style.transform = tf;
      });
      (st.fcards || []).forEach((cd) => {
        /* a slow pan across the picture and a gentle push: the view keeps changing for the whole beat */
        const e = eo(k), pos = cd.dir > 0 ? 18 + 64 * e : 82 - 64 * e;
        cd.im.style.objectPosition = cd.vertical ? `50% ${10 + 25 * e}%` : `${pos}% 40%`;
        cd.im.style.transformOrigin = "50% 40%";
        cd.im.style.transform = `scale(${1 + 0.1 * k * T().push})`;
      });
      st.ln.style.transform = `scaleX(${eo(seg(t, 0, 0.6 / m.speed))})`;
      if (st.k) { const q = eo(seg(t, 0, 0.35)); st.k.style.opacity = q; st.k.style.transform = `translateY(${(1 - q) * -14}px)`; }
      st.lines.forEach((o) => {
        const q = eo(seg(t, o.t0, o.t0 + 0.38 / m.speed));
        o.d.style.opacity = q; o.d.style.transform = `translateY(${(1 - q) * 34 * u * m.rise}px) scale(${0.94 + 0.06 * q})`;
      });
      if (st.m === "dust") {
        const H = c.H + 200 * u;
        st.dust.forEach((d) => { const ph = (t * 0.18 * d.sp + d.ph) % 1; d.d.style.transform = `translate(${d.x * c.W + Math.sin(t * d.sp + d.ph * 9) * d.sw * u}px,${-100 * u + ph * H}px)`; d.d.style.opacity = 0.6; });
      } else if (st.m === "rings") {
        st.rings.forEach((d, i) => { const ph = (t * 0.8 + i / 4) % 1, r = (40 + ph * 460) * u; L.pos(d, st.rx - r, st.ry - r, r * 2, r * 2); d.style.opacity = (1 - ph) * 0.9; });
        st.dot.style.transform = `scale(${1 + 0.15 * Math.sin(t * 9)})`;
      } else if (st.m === "route") {
        const { x0, y0, x1, y1, cx, cy } = st.rt, a = eo(clamp(t / Math.max(0.5, c.dur * 0.85), 0, 1));
        const bx = (1 - a) * (1 - a) * x0 + 2 * (1 - a) * a * cx + a * a * x1, by = (1 - a) * (1 - a) * y0 + 2 * (1 - a) * a * cy + a * a * y1;
        const tx = 2 * (1 - a) * (cx - x0) + 2 * a * (x1 - cx), ty = 2 * (1 - a) * (cy - y0) + 2 * a * (y1 - cy);
        st.plane.setAttribute("transform", `translate(${bx},${by}) rotate(${Math.atan2(ty, tx) * 180 / Math.PI}) scale(1.3)`);
      } else if (st.m === "stamp") {
        const q = eo(seg(t, st.sT, st.sT + 0.35)); st.stamp.style.opacity = q; st.stamp.style.transform = `scale(${1.25 - 0.25 * q}) rotate(${-4 * q}deg)`;
      } else if (st.m === "date") {
        const q = eo(seg(t, 0, 0.4)); st.date.style.opacity = q; st.date.style.transform = `scale(${1.1 - 0.1 * q})`;
      }
    },
    cues: (c) => [{ lt: 0.05, type: "tick" }, ...((c.p.srcs || []).slice(1).map((it, k, a) => ({ lt: when(c, it, k + 1, a.length + 1, 0.3, c.dur * 0.7), type: "swish", lvl: 2 })))],
  };

  /* ------------------------------------------------------------ statement */
  S.statement = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { lines: [] };
      ground(root, c);
      if (p.src) { const g = el("div", "abs", root); L.pos(g, 0, 0, c.W, c.H); g.style.overflow = "hidden"; st.pic = photo(g, p.src, c, `filter:saturate(.8) brightness(${p.bright || 0.4})`); }
      const b = el("div", "abs", root); L.pos(b, c.safe.x + 50 * u, c.safe.y, c.safe.w - 100 * u, c.safe.h);
      b.style.cssText += `;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center`;
      (p.lines || []).forEach((tx, i) => {
        const it = typeof tx === "string" ? { text: tx } : tx, e = el("div", "", b, mark(it.text));
        e.style.cssText = `color:${C.ink};${fnt(null, (it.size || p.size || 92) * u)};margin:${16 * u}px 0;text-shadow:0 ${6 * u}px ${30 * u}px rgba(0,0,0,.6)`;
        st.lines.push({ e, it, k: i });
      });
      const n = st.lines.length; st.lines.forEach((s) => { s.t0 = s.k === 0 ? -1 : when(c, s.it, s.k, n, 0, Math.max(0.6, c.dur * 0.62)); });
      return st;
    },
    update(st, t, c) {
      const fl = c.p.floor != null ? c.p.floor : T().dim * 0.8;
      st.lines.forEach((s) => rise(s.e, t, s.t0, 0.55, 30 * c.u, s.k === 0 ? 0 : fl));
      if (st.pic) st.pic.style.transform = `scale(${1.02 + t * 0.01 * T().push})`;
    },
    cues: (c) => { const n = (c.p.lines || []).length; return (c.p.lines || []).slice(1).map((it, k) => ({ lt: when(c, typeof it === "string" ? {} : it, k + 1, n, 0, Math.max(0.6, c.dur * 0.62)), type: "swish", lvl: 2 })); },
  };

  /* ------------------------------------------------------------ cards */
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
        cardStyle(e, c, false);
        e.style.cssText += `;padding:${24 * u}px ${28 * u}px;display:flex;flex-direction:column;justify-content:center;gap:${12 * u}px;overflow:hidden`;
        if (T().card === "sticker") e.style.transform = `rotate(${((k % 3) - 1) * 1.2}deg)`;
        if (it.src) { const im = el("div", "", e); im.style.cssText = `flex:1;min-height:0;border-radius:${Math.min(T().radius, 16) * u}px;overflow:hidden;position:relative`; photo(im, it.src, c); }
        if (it.tag) { const q = el("div", "", e, L.esc(it.tag)); q.style.cssText = `color:${C.accent};font:800 ${30 * u}px var(--mono);letter-spacing:.04em`; }
        const b = el("div", "", e, mark(it.t || "")); b.style.cssText = `color:${C.ink};${fnt(null, (p.t_size || 54) * u)}`;
        if (it.d) { const d = el("div", "", e, mark(it.d)); d.style.cssText = `color:${C.muted};font:500 ${(p.d_size || 36) * u}px/1.25 var(--sans)`; }
        st.cards.push({ e, t0: when(c, it, k, n, 0.2, c.dur * 0.78) });
      });
      return st;
    },
    update(st, t, c) {
      headingAt(st.head, t + 0.4);
      const dim = T().dim;
      st.cards.forEach((s, k) => {
        const a = eo(seg(t, s.t0, s.t0 + 0.45)), nx = st.cards[k + 1], hot = t >= s.t0 && (!nx || t < nx.t0);
        s.e.style.opacity = dim + (1 - dim) * a;
        const base = s.e.dataset.rot || (s.e.dataset.rot = (s.e.style.transform.match(/rotate\([^)]*\)/) || [""])[0]);
        s.e.style.transform = `${base} translateY(${(1 - a) * 10 * c.u * T().rise}px)`;
        s.e.style.borderColor = hot ? C.accent : L.hexA(C.ink, T().card === "sticker" ? 0.9 : 0.24);
        if (T().shadow === "glow") s.e.style.boxShadow = `0 0 ${(hot ? 44 : 18) * c.u}px ${L.hexA(C.accent, hot ? 0.55 : 0.2)}`;
      });
    },
    cues: (c) => (c.p.items || []).map((it, k, a) => ({ lt: when(c, it, k, a.length, 0.2, c.dur * 0.78), type: "swish", lvl: 2 })),
  };

  /* ------------------------------------------------------------ flow */
  S.flow = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { nodes: [], arrows: [] };
      ground(root, c); st.head = heading(root, c, p, c.safe.y);
      const items = p.nodes || [], n = items.length, g = 96 * u, w = (c.safe.w - g * (n - 1)) / Math.max(1, n), h = Math.min(c.safe.h * 0.56, (p.h || 430) * u);
      const top = st.head.bottom, y = top + (c.safe.y + c.safe.h - top - h) / 2;
      const svg = L.svg("svg", { width: c.W, height: c.H }, root); svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible";
      items.forEach((it, k) => {
        const x = c.safe.x + k * (w + g), e = el("div", "abs", root); L.pos(e, x, y, w, h);
        cardStyle(e, c, false);
        e.style.cssText += `;padding:${26 * u}px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:${12 * u}px;overflow:hidden`;
        if (it.src) { const im = el("div", "", e); im.style.cssText = `width:100%;flex:1;min-height:0;border-radius:${Math.min(T().radius, 16) * u}px;overflow:hidden;position:relative`; photo(im, it.src, c); }
        if (it.glyph) { const q = el("div", "", e, L.esc(it.glyph)); q.style.cssText = `color:${C.accent};font:800 ${(it.glyph_size || 64) * u}px var(--mono)`; }
        const b = el("div", "", e, mark(it.label || "")); b.style.cssText = `color:${C.ink};${fnt(null, (p.size || 46) * u)}`;
        if (it.sub) { const d = el("div", "", e, mark(it.sub)); d.style.cssText = `color:${C.muted};font:500 ${32 * u}px/1.24 var(--sans)`; }
        st.nodes.push({ e, t0: when(c, it, k, n, 0.2, c.dur * 0.75) });
        if (k < n - 1) {
          const x1 = x + w + 10 * u, x2 = x + w + g - 12 * u, ym = y + h / 2;
          const ln = L.svg("line", { x1, y1: ym, x2, y2: ym, stroke: C.accent, "stroke-width": 7 * u, filter: "url(#fv-bloom)", "stroke-linecap": "round" }, svg);
          const hd = L.svg("path", { d: `M${x2 - 18 * u} ${ym - 16 * u} L${x2} ${ym} L${x2 - 18 * u} ${ym + 16 * u}`, fill: "none", stroke: C.accent, "stroke-width": 7 * u, "stroke-linecap": "round" }, svg);
          st.arrows.push({ ln, hd, x1, x2, k });
        }
      });
      return st;
    },
    update(st, t, c) {
      headingAt(st.head, t + 0.4);
      const dim = T().dim;
      st.nodes.forEach((s, k) => {
        const a = eo(seg(t, s.t0, s.t0 + 0.45)), nx = st.nodes[k + 1], hot = t >= s.t0 && (!nx || t < nx.t0);
        s.e.style.opacity = dim + (1 - dim) * a; s.e.style.transform = `scale(${0.97 + 0.03 * a})`;
        s.e.style.borderColor = t >= s.t0 ? C.accent : L.hexA(C.ink, 0.22);
        if (T().shadow === "glow" || T().shadow === "soft") s.e.style.boxShadow = hot ? `0 0 ${50 * c.u}px ${L.hexA(C.accent, 0.5)}` : "none";
      });
      st.arrows.forEach((r) => {
        const t0 = st.nodes[r.k + 1].t0 - 0.35, p = eo(seg(t, t0, t0 + 0.35));
        r.ln.setAttribute("x2", r.x1 + (r.x2 - r.x1) * p); r.ln.style.opacity = p > 0 ? 1 : 0; r.hd.style.opacity = p >= 0.98 ? 1 : 0;
      });
    },
    cues: (c) => (c.p.nodes || []).map((it, k, a) => ({ lt: when(c, it, k, a.length, 0.2, c.dur * 0.75), type: k ? "zap" : "swish", lvl: 2 })),
  };

  /* ------------------------------------------------------------ bold */
  const spring = (t, t0) => { const x = (t - t0) * 1.4; return x <= 0 ? 0 : 1 - Math.exp(-7.5 * x) * Math.cos(12 * x); };
  S.bold = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { lines: [] };
      const bg = el("div", "abs", root); L.pos(bg, 0, 0, c.W, c.H); bg.style.background = p.g || C.bg;
      const gnd = p.g || C.bg, ink = L.isDark(gnd) ? "#ffffff" : "#111111", sh = p.shape || "circle", sc = p.shape_color || C.accent, R = Math.min(c.W, c.H) * 0.62;
      if (sh !== "none") {
        st.rot = sh !== "bar" && sh !== "circle"; const e = (st.shape = el("div", "abs", root)); L.pos(e, c.W / 2 - R / 2, c.H * 0.42 - R / 2, R, R);
        e.style.cssText += sh === "bar" ? `;height:${R * 0.3}px;top:${c.H * 0.42 - R * 0.15}px;width:${c.W}px;left:0;background:${sc}` : sh === "burst" ? `;background:repeating-conic-gradient(${sc} 0deg 10deg,transparent 10deg 20deg);border-radius:50%;opacity:.9` : `;border-radius:50%;background:${sc}`;
      }
      const b = el("div", "abs", root); L.pos(b, c.safe.x, c.safe.y, c.safe.w, c.safe.h);
      b.style.cssText += ";display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:" + 10 * u + "px";
      (p.lines || []).forEach((tx, i) => {
        const it = typeof tx === "string" ? { text: tx } : tx, kind = it.color || (i % 2 ? "accent" : "ink");
        const e = el("div", "", b, L.esc(it.text));
        const chip = kind === "chip";
        e.style.cssText = `${fnt(null, (it.size || 150) * u)};color:${chip ? onAcc() : kind === "accent" ? C.accent : ink};text-shadow:0 ${5 * u}px 0 rgba(0,0,0,.18);${chip ? `background:${C.accent};padding:0 ${0.18 * 150 * u}px;` : ""}white-space:nowrap`;
        st.lines.push({ e, t0: when(c, it, i, (p.lines || []).length, 0.05, c.dur * 0.7) });
      });
      return st;
    },
    update(st, t, c) {
      if (st.shape) st.shape.style.transform = `scale(${0.2 + 0.8 * spring(t, 0)}) ${st.rot ? `rotate(${t * 6 * L.T.speed}deg)` : ""}`;
      st.lines.forEach((s) => { const q = spring(t, s.t0); s.e.style.opacity = Math.min(1, q * 3); s.e.style.transform = `scale(${0.4 + 0.6 * q}) translateY(${(1 - Math.min(1, q)) * 40 * c.u}px)`; });
    },
    cues: (c) => (c.p.lines || []).map((it, k, a) => ({ lt: when(c, typeof it === "string" ? {} : it, k, a.length, 0.05, c.dur * 0.7), type: k ? "thump" : "swish", lvl: 2 })),
  };

  /* ------------------------------------------------------------ site */
  function browser(parent, src, url, w, h, u) {
    const b = el("div", "abs", parent); L.pos(b, 0, 0, w, h); b.dataset.nolint = "";
    b.style.cssText += `;border-radius:${14 * u}px;overflow:hidden;background:#17181b;box-shadow:0 ${26 * u}px ${70 * u}px rgba(0,0,0,.7),0 0 0 ${2 * u}px rgba(255,255,255,.18)`;
    const bar = el("div", "abs", b), bh = 44 * u; L.pos(bar, 0, 0, w, bh);
    bar.style.cssText += `;background:#26282d;display:flex;align-items:center;gap:${9 * u}px;padding-left:${16 * u}px;box-sizing:border-box`;
    ["#ff5f57", "#febc2e", "#28c840"].forEach((k) => { const d = el("div", "", bar); d.style.cssText = `width:${13 * u}px;height:${13 * u}px;border-radius:50%;background:${k};flex:none`; });
    const a = el("div", "", bar, L.esc(url || "")); a.style.cssText = `margin-left:${14 * u}px;padding:${5 * u}px ${18 * u}px;border-radius:${14 * u}px;background:#15161a;color:#c9cbd1;font:500 ${18 * u}px var(--sans);white-space:nowrap`;
    const box = el("div", "abs", b); L.pos(box, 0, bh, w, h - bh); box.style.overflow = "hidden";
    b.img = photo(box, src, null, "object-position:top");
    return b;
  }
  S.site = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, st = { shots: [], notes: [] };
      ground(root, c);
      const shots = p.shots || [{ src: p.src, url: p.url }];
      const gap = 56 * u, w = Math.min(c.safe.w * 0.62, 1040 * u), h = Math.min(c.safe.h * 0.94, w * 0.68), x = c.safe.x, y = c.safe.y + (c.safe.h - h) / 2;
      shots.forEach((sh, k) => {
        const wrap = el("div", "abs", root); L.pos(wrap, x, y, w, h);
        st.shots.push({ wrap, br: browser(wrap, sh.src, sh.url, w, h, u), t0: k === 0 ? -1 : when(c, sh, k, shots.length, 0.4, c.dur * 0.72), k });
      });
      const cx = x + w + gap, cw = c.safe.x + c.safe.w - cx, col = el("div", "abs", root); L.pos(col, cx, c.safe.y, cw, c.safe.h);
      col.style.cssText += `;display:flex;flex-direction:column;justify-content:center;gap:${24 * u}px`;
      if (p.kicker) { st.k = kickerEl(col, p.kicker, c, false); st.k.style.alignSelf = "flex-start"; }
      if (p.title) { st.h = el("div", "", col, mark(p.title)); st.h.style.cssText = `color:${C.ink};${fnt(null, (p.title_size || 68) * u)}`; }
      (p.notes || []).forEach((nt, k, a) => {
        const it = typeof nt === "string" ? { text: nt } : nt, e = el("div", "", col, mark(it.text));
        e.style.cssText = `padding:${14 * u}px ${20 * u}px;border-left:${6 * u}px solid ${C.accent};background:${L.hexA(C.surface, 0.92)};border-radius:${Math.min(T().radius, 12) * u}px;color:${C.ink};font:600 ${34 * u}px/1.22 var(--sans)`;
        st.notes.push({ e, t0: when(c, it, k, a.length, 0.5, c.dur * 0.8) });
      });
      return st;
    },
    update(st, t, c) {
      if (st.k) rise(st.k, t, -0.3, 0.3, 14); if (st.h) rise(st.h, t, -0.2, 0.4, 20);
      for (const s of st.shots) {
        const a = eo(seg(t, s.t0, s.t0 + 0.45));
        s.wrap.style.opacity = s.k === 0 ? 1 : a;
        s.wrap.style.transform = s.k === 0 ? "" : `translateY(${(1 - a) * 60 * c.u}px) scale(${0.97 + 0.03 * a})`;
        s.br.img.style.transform = `scale(${1 + Math.max(0, t - s.t0) * 0.006})`;
      }
      for (const s of st.notes) rise(s.e, t, s.t0, 0.45, 18 * c.u);
    },
    cues: (c) => [{ lt: 0, type: "swish", lvl: 2 }, ...(c.p.shots || []).slice(1).map((sh, k, a) => ({ lt: when(c, sh, k + 1, a.length + 1, 0.4, c.dur * 0.72), type: "thump", lvl: 2 }))],
  };
})();
