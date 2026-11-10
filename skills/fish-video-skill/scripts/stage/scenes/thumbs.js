/* Thumbnail layouts: `thumbnail` with params.layout.

   The plain `thumbnail` scene (cards.js) is still what runs when no layout is named. With
   params.layout this file draws one of five designed templates, at any size (1280x720 for a
   video thumbnail, 1080x1920 for a vertical cover). Used by `fishvideo thumb make`.

     layout: subject   huge title in one accent word + a subject (cut-out with outline and glow, or a framed picture)
             number    one giant figure, a short label under it
             split     before / after on a diagonal split, each half labelled
             caption   a full-bleed frame, a dark scrim, the caption low and left
             frame     the best frame of the video in a card, the title beside it
             road      the house thumbnail (`fishvideo thumbnail`): tag, huge two-tone headline, audience line, and logo or picture
                       tiles along a glowing road (params.tiles); see the road() comment
             insider   the light kinetic-explainer cover: one hero (cut-out, card or logo network), lead / huge keyword / mid /
                       black chip, scattered accent asterisks; see the insider() comment

   params: title, accent (the word to mark; "*word*" also marks), kicker, badge,
           image (subject or frame, project path), baked (true: the PNG already has its outline and glow),
           number, label (number layout), before, after, before_label, after_label (split), bg (dark | light)

   Every layout keeps its text inside c.safe, keeps the bottom-right corner free of text (the duration
   stamp a feed puts there) and is a pure function of time: nothing moves. */
(function () {
  "use strict";
  const S = (window.SCENES = window.SCENES || {});
  const H = L.H;
  const { el, C } = L;
  const base = S.thumbnail;

  /* Fitting is measured twice: once at build and once again at the first frame, when the fonts and the
     layout are final. Both are pure functions of the page, so the picture never depends on timing. */
  const fits = [];
  function fit(h, w, lines, min, after) {
    const nlines = () => new Set([...h.querySelectorAll(".fv-sw")].map((e) => e.offsetTop)).size || 1;
    const run = () => {
      let px = parseFloat(h.style.fontSize);
      for (let i = 0; i < 40 && px > min && (h.scrollWidth > w + 1 || nlines() > lines); i++) { px *= 0.96; h.style.fontSize = px + "px"; }
      if (after) after();
    };
    run();
    fits.push(run);
  }
  const k = (c) => (c.P ? c.W / 1080 : c.H / 720);
  const zones = (c, art) => {
    const s = c.safe;
    if (!art) return { text: { x: s.x, y: s.y, w: s.w, h: s.h }, art: null, center: true };
    if (c.P) return { text: { x: s.x, y: s.y, w: s.w, h: s.h * 0.4 }, art: { x: s.x, y: s.y + s.h * 0.42, w: s.w, h: s.h * 0.58 }, center: false };
    return { text: { x: s.x, y: s.y, w: s.w * 0.52, h: s.h }, art: { x: s.x + s.w * 0.54, y: s.y, w: s.w * 0.46, h: s.h }, center: false };
  };
  const box = (root, z) => { const b = el("div", "abs", root); L.pos(b, z.x, z.y, z.w, z.h); return b; };
  const isCut = (src, p) => /\.(png|webp|svg)$/i.test(String(src || "")) && p.hero_cut !== false;

  function background(root, c, dark, tint) {
    const bg = el("div", "abs", root); L.pos(bg, 0, 0, c.W, c.H);
    const at = c.P ? "50% 70%" : "76% 50%";
    bg.style.background = dark ? `radial-gradient(ellipse 70% 80% at ${at}, ${L.hexA(tint || C.accent, 0.34)} 0%, #0b0b0c 66%)` : `radial-gradient(ellipse 70% 80% at ${at}, #ffffff 0%, ${C.bg} 74%)`;
    return bg;
  }

  /* the title as words, the marked one on an accent plate */
  function titleHTML(p, c) {
    const acc = String(p.accent || "").toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
    return String(p.title || c.brand.name || "").split(/\s+/).filter(Boolean).map((w) => {
      const marked = /^\*.*\*[.,!?:;]*$/.test(w), bare = w.replace(/\*/g, "");
      const hit = marked || (acc && bare.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "") === acc);
      return hit ? `<span class="fv-sw" style="display:inline-block;background:${C.accent};color:${L.isDark(C.accent) ? "#fff" : "#0b0b0b"};padding:0 .14em .04em;margin:0 -.02em">${L.esc(bare)}</span>` : `<span class="fv-sw" style="display:inline-block">${L.esc(bare)}</span>`;
    }).join(" ");
  }

  function kicker(parent, p, c, ink) {
    if (!p.kicker) return null;
    const e = el("div", "", parent, L.esc(p.kicker));
    e.style.cssText += `;font:800 ${30 * k(c)}px var(--display);letter-spacing:.02em;text-transform:uppercase;color:${ink};opacity:.85`;
    return e;
  }
  function badge(parent, p, c, dark, ink, align) {
    const t = String(p.badge || "").trim();
    if (!t || /^(none|n\/a|null|-+)$/i.test(t)) return null;
    const e = el("div", "", parent, L.esc(t));
    e.style.cssText += `;align-self:${align};font:800 ${30 * k(c)}px var(--display);color:${dark ? "#0b0b0b" : "#fff"};background:${ink};padding:.24em .6em;border-radius:.3em`;
    return e;
  }

  /* a column of kicker, title, badge: the title as large as the zone allows, the column centred in it */
  function textColumn(root, c, z, p, dark, o = {}) {
    const ink = o.ink || L.inkOn(dark), b = box(root, z), u = k(c);
    b.style.cssText += `;display:flex;flex-direction:column;gap:${16 * u}px;justify-content:center;${z.center || o.center ? "align-items:center;text-align:center" : ""}`;
    b.style.height = "auto";
    kicker(b, p, c, ink);
    const h = el("div", "", b, titleHTML(p, c));
    h.style.cssText += `;font:900 100px/1.03 var(--display);letter-spacing:-.035em;text-transform:${o.upper === false ? "none" : "uppercase"};color:${ink};text-shadow:0 ${5 * u}px ${18 * u}px ${dark ? "rgba(0,0,0,.7)" : "rgba(255,255,255,.3)"}`;
    L.fitHero(h, { w: z.w, lines: o.lines || 3, max: (o.max || 220) * u, min: 56 * u });
    badge(b, p, c, dark, ink, z.center || o.center ? "center" : "flex-start");
    const place = () => { b.style.top = z.y + (z.h - b.offsetHeight) / 2 + "px"; };
    const run = () => { let px = parseFloat(h.style.fontSize); while (b.offsetHeight > z.h && px > 48 * u) { px -= 4 * u; h.style.fontSize = px + "px"; } place(); };
    fit(h, z.w, o.lines || 3, 48 * u, run);
    return { box: b, h };
  }

  /* ------------------------------------------------------------ subject */
  function subject(root, c) {
    const p = c.p, u = k(c), dark = p.bg ? p.bg === "dark" : true;
    background(root, c, dark);
    const src = p.image || p.hero || p.src, z = zones(c, !!src);
    if (src) {
      const fr = box(root, z.art), url = L.projUrl(src), img = el("img", "", fr);
      L.setImg(img, url);
      if (isCut(src, p)) {
        img.style.cssText = "width:100%;height:100%;object-fit:contain";
        fr.style.filter = p.baked ? "" : L.cutFilter({ outline: 6 * u, shadow: { x: 12 * u, y: 16 * u, blur: 26 * u, a: 0.6 } }) + ` drop-shadow(0 0 ${34 * u}px ${L.hexA(C.accent, 0.55)})`;
      } else {
        const pad = 14 * u;
        L.pos(fr, z.art.x + pad, z.art.y + pad, z.art.w - 2 * pad, z.art.h - 2 * pad);
        fr.style.cssText += `;overflow:hidden;transform:rotate(3deg);border:${6 * u}px solid ${C.accent};box-shadow:0 ${14 * u}px ${44 * u}px rgba(0,0,0,.6)`;
        img.style.cssText = "width:100%;height:100%;object-fit:cover;filter:contrast(1.15) saturate(1.1)";
      }
    }
    textColumn(root, c, z.text, p, dark);
    return {};
  }

  /* ------------------------------------------------------------ number */
  function number(root, c) {
    const p = c.p, u = k(c), dark = p.bg ? p.bg === "dark" : true, ink = L.inkOn(dark);
    background(root, c, dark);
    const s = c.safe, b = box(root, { x: s.x, y: s.y, w: s.w, h: s.h });
    b.style.cssText += `;display:flex;flex-direction:column;justify-content:center;align-items:${c.P ? "center" : "flex-start"};gap:${10 * u}px;${c.P ? "text-align:center" : ""}`;
    b.style.height = "auto";
    kicker(b, p, c, ink);
    /* "66 days": the figure big, the unit beside it in the ink colour at a third of the size */
    const m = /^\s*([^\p{L}]*?\d[^\p{L}]*?)\s*(\p{L}.*)?$/u.exec(String(p.number || "").trim() || "0");
    const n = el("div", "", b, `${L.esc(m ? m[1] : String(p.number))}${m && m[2] ? `<span style="font-size:.34em;letter-spacing:0;margin-left:.2em;color:${ink};text-transform:uppercase;text-shadow:none">${L.esc(m[2])}</span>` : ""}`);
    n.style.cssText += `;font:900 100px/.95 var(--display);letter-spacing:-.05em;color:${C.accent};text-shadow:0 ${8 * u}px ${28 * u}px ${L.hexA(C.accent, 0.45)}`;
    L.fitHero(n, { w: s.w * (c.P ? 1 : 0.9), lines: 1, max: (c.P ? 420 : 400) * u, min: 120 * u });
    const lab = el("div", "", b, titleHTML({ title: p.label || p.title, accent: p.accent }, c));
    lab.style.cssText += `;font:900 100px/1.04 var(--display);letter-spacing:-.03em;text-transform:uppercase;color:${ink}`;
    L.fitHero(lab, { w: s.w * (c.P ? 1 : 0.72), lines: 2, max: Math.min(parseFloat(n.style.fontSize) / 3, 130 * u), min: 48 * u });
    badge(b, p, c, dark, ink, c.P ? "center" : "flex-start");
    const run = () => { let px = parseFloat(n.style.fontSize); while (b.offsetHeight > s.h && px > 100 * u) { px -= 8 * u; n.style.fontSize = px + "px"; } b.style.top = s.y + (s.h - b.offsetHeight) / 2 + "px"; };
    fit(lab, s.w * (c.P ? 1 : 0.72), 2, 40 * u);
    fit(n, s.w * (c.P ? 1 : 0.9), 1, 100 * u, run);
    return {};
  }

  /* ------------------------------------------------------------ split */
  function split(root, c) {
    const p = c.p, u = k(c), dark = true, W = c.W, Hh = c.H;
    background(root, c, dark);
    const pic = (parent, src, css, x, y, w, h, clip) => {
      const f = el("div", "abs", parent); L.pos(f, x, y, w, h);
      f.style.cssText += `;overflow:hidden;clip-path:${clip};background:#222`;
      if (src) { const img = el("img", "", f); img.style.cssText = `width:100%;height:100%;object-fit:cover;${css}`; L.setImg(img, L.projUrl(src)); }
      return f;
    };
    const a = p.before || p.image, b = p.after || p.image;
    const gap = 8 * u;
    if (c.P) {
      pic(root, a, p.before ? "" : "filter:grayscale(1) brightness(.6) blur(3px)", 0, 0, W, Hh, `polygon(0 0, 100% 0, 100% ${50 - 4}%, 0 ${50 + 4}%)`);
      pic(root, b, p.after ? "" : "filter:saturate(1.25) contrast(1.1)", 0, 0, W, Hh, `polygon(0 ${50 + 4}%, 100% ${50 - 4}%, 100% 100%, 0 100%)`);
    } else {
      pic(root, a, p.before ? "" : "filter:grayscale(1) brightness(.6) blur(3px)", 0, 0, W, Hh, `polygon(0 0, 54% 0, 46% 100%, 0 100%)`);
      pic(root, b, p.after ? "" : "filter:saturate(1.25) contrast(1.1)", 0, 0, W, Hh, `polygon(54.6% 0, 100% 0, 100% 100%, 46.6% 100%)`);
    }
    /* labels */
    const s = c.safe;
    const chip = (txt, x, y, alignRight, hot) => {
      const e = el("div", "abs", root, L.esc(txt)); L.pos(e, x, y);
      e.style.cssText += `;font:900 ${44 * u}px var(--display);letter-spacing:.04em;text-transform:uppercase;padding:.2em .6em;border-radius:.3em;color:${hot ? (L.isDark(C.accent) ? "#fff" : "#0b0b0b") : "#f5f5f5"};background:${hot ? C.accent : "rgba(20,20,22,.82)"};${alignRight ? "transform:translateX(-100%)" : ""}`;
    };
    chip(p.before_label || "Before", s.x, s.y, false, false);
    if (c.P) chip(p.after_label || "After", s.x, s.y + s.h * 0.52, false, true);
    else chip(p.after_label || "After", s.x + s.w, s.y, true, true);
    /* the title on a plate across the lower part, short of the bottom-right corner */
    const plate = el("div", "abs", root); const pw = c.P ? s.w : s.w * 0.7;
    L.pos(plate, s.x, 0, pw);
    plate.style.cssText += `;background:rgba(11,11,12,.86);border-left:${10 * u}px solid ${C.accent};padding:${16 * u}px ${28 * u}px;border-radius:${6 * u}px`;
    const h = el("div", "", plate, titleHTML(p, c));
    h.style.cssText += `;font:900 100px/1.03 var(--display);letter-spacing:-.03em;text-transform:uppercase;color:#f5f5f5`;
    L.fitHero(h, { w: pw - 56 * u, lines: 2, max: 120 * u, min: 52 * u });
    fit(h, pw - 56 * u, 2, 44 * u, () => { plate.style.top = s.y + s.h - plate.offsetHeight - (c.P ? 0 : 4 * u) + "px"; });
    return {};
  }

  /* ------------------------------------------------------------ caption */
  function caption(root, c) {
    const p = c.p, u = k(c), W = c.W, Hh = c.H, s = c.safe, dark = true;
    const bg = el("div", "abs", root); L.pos(bg, 0, 0, W, Hh);
    bg.style.background = `radial-gradient(ellipse 80% 90% at 30% 40%, ${L.hexA(C.accent, 0.4)}, #0b0b0c 75%)`;
    if (p.image) { const img = el("img", "abs", root); L.pos(img, 0, 0, W, Hh); img.style.cssText += `;object-fit:cover;transform:scale(1.04);filter:blur(${5 * u}px) brightness(.8) saturate(1.1)`; L.setImg(img, L.projUrl(p.image)); }  /* soft: the frame carries its own words, which must not compete with the caption */
    const sc = el("div", "abs", root); L.pos(sc, 0, 0, W, Hh);
    sc.style.background = (c.P ? "linear-gradient(0deg, rgba(8,8,9,.96) 0%, rgba(8,8,9,.9) 46%, rgba(8,8,9,.55) 62%, rgba(8,8,9,0) 80%)" : "linear-gradient(90deg, rgba(8,8,9,.94) 0%, rgba(8,8,9,.9) 52%, rgba(8,8,9,.6) 66%, rgba(8,8,9,0) 86%)");
    const corner = el("div", "abs", root); L.pos(corner, W * 0.7, Hh * 0.72, W * 0.3, Hh * 0.28);
    corner.style.background = "radial-gradient(ellipse at 100% 100%, rgba(8,8,9,.8), rgba(8,8,9,0) 70%)"; /* the corner a feed covers with a time stamp */
    const z = c.P ? { x: s.x, y: s.y + s.h * 0.48, w: s.w, h: s.h * 0.52 } : { x: s.x, y: s.y, w: s.w * 0.58, h: s.h };
    textColumn(root, c, z, p, dark, { ink: "#f5f5f5", lines: 3, max: 190 });
    return {};
  }

  /* ------------------------------------------------------------ frame */
  function frame(root, c) {
    const p = c.p, u = k(c), dark = p.bg ? p.bg === "dark" : true;
    background(root, c, dark);
    const src = p.image, z = zones(c, !!src);
    if (src) {
      const fr = box(root, z.art), img = el("img", "", fr), pad = 16 * u;
      L.pos(fr, z.art.x + pad, z.art.y + pad, z.art.w - 2 * pad, z.art.h - 2 * pad);
      fr.style.cssText += `;overflow:hidden;transform:rotate(-2deg);border:${8 * u}px solid ${dark ? "#f5f5f5" : "#fff"};border-radius:${10 * u}px;box-shadow:0 ${18 * u}px ${50 * u}px rgba(0,0,0,.65),0 0 0 ${4 * u}px ${C.accent}`;
      img.style.cssText = "width:100%;height:100%;object-fit:cover";
      L.setImg(img, L.projUrl(src));
    }
    textColumn(root, c, z.text, p, dark);
    return {};
  }

  /* ------------------------------------------------------------ road */
  /* The house thumbnail: a short tag above, a huge two-tone headline on the left, an audience line below, and on the right a
     smooth glowing road (uniform Catmull-Rom through the tile centres, open-ended so it has no kink) passing through tiles.
     A tile is a brand logo (simple-icons path; the marks belong to their owners) or a licensed picture. Dark glow ground; the
     theme supplies the accent colour and the display font.
     params: tag, title, accent (the big first words), sub (audience line; *word* is marked), tiles [{d, hex, tile, title} | {src}] */
  const ROAD = [[730, 625], [915, 600], [1140, 500], [960, 395], [745, 300], [960, 185], [1175, 95]];
  const roadPoints = (n) => {
    if (n >= ROAD.length) return ROAD.slice();
    if (n === 1) return [ROAD[3]];
    return Array.from({ length: n }, (_, i) => ROAD[Math.round((i * (ROAD.length - 1)) / (n - 1))]);
  };
  /* pictures: one big hero tile and up to two smaller ones (design units: 1280x720 landscape, 1080x1920 portrait); logos: a row of small tiles */
  const PICS_L = [{ x: 790, y: 600, s: 170 }, { x: 910, y: 330, s: 330 }, { x: 1160, y: 120, s: 160 }];
  const PICS_P = [{ x: 250, y: 1420, s: 290 }, { x: 540, y: 950, s: 470 }, { x: 800, y: 1520, s: 290 }];
  /* thumbnail type is always heavy: the theme's display face only when it is itself a heavy one, else Inter 900 (never a distressed or light face) */
  const HEAVY = new Set(["Anton", "Archivo Black", "Oswald"]);
  const heavyFamily = () => { const d = (L.T && getComputedStyle(document.documentElement).getPropertyValue("--display") || "").split(",")[0].replace(/["']/g, "").trim(); return HEAVY.has(d) ? "var(--display)" : "'Inter', var(--sans)"; };
  const STOP = new Set("a an the of and or but in on at to for with by from as is are was were be been it its this that these those vs".split(" "));
  function road(root, c) {
    const p = c.p, k = c.P ? c.W / 1080 : c.H / 720, W = c.W, Hh = c.H, s = c.safe;
    const bgc = L.isDark(C.bg) ? C.bg : "#0b0b0e", ink = "#ffffff", acc = C.accent;
    const bg = el("div", "abs", root); L.pos(bg, 0, 0, W, Hh);
    const gx = c.P ? W * 0.5 : W * 0.69, gy = c.P ? Hh * 0.62 : Hh * 0.5;
    bg.style.background = `radial-gradient(${700 * k}px ${520 * k}px at ${gx}px ${gy}px, ${L.hexA(acc, 0.42)}, transparent 70%),radial-gradient(${500 * k}px ${400 * k}px at ${60 * k}px ${Hh - 20 * k}px, ${L.hexA(acc, 0.16)}, transparent 70%),${bgc}`;
    const grid = el("div", "abs", root); L.pos(grid, 0, 0, W, Hh);
    grid.style.cssText += `;background-image:linear-gradient(#ffffff0a 1px,transparent 1px),linear-gradient(90deg,#ffffff0a 1px,transparent 1px);background-size:${64 * k}px ${64 * k}px;-webkit-mask-image:radial-gradient(ellipse at ${gx}px ${gy}px,#000 20%,transparent 75%)`;
    const all = (p.tiles || []);
    const pics = all.length > 0 && all.every((t) => t.src);
    const tiles = all.slice(0, pics ? 3 : c.P ? 5 : 7);
    const n = tiles.length, ox = c.P ? 0 : (W - 1280 * k) / 2;
    /* tile centres and sizes. Pictures: [small, hero, small] in road order; the first given picture is the hero. */
    let spots;
    if (pics) {
      const T = (c.P ? PICS_P : PICS_L);
      const order = n >= 3 ? [1, 0, 2] : n === 2 ? [1, 0] : [1];                  /* tiles[0] -> hero (T[1]), tiles[1] -> T[0], tiles[2] -> T[2] */
      spots = order.map((ti) => ({ x: T[ti].x * k + ox, y: T[ti].y * k, size: T[ti].s * k }));
      spots = spots.map((sp, i) => ({ ...sp, idx: order[i] }));
      const byIdx = {}; tiles.forEach((t, i) => { byIdx[[1, 0, 2][i]] = t; });
      spots = spots.map((sp) => ({ ...sp, tile: byIdx[sp.idx] })).filter((sp) => sp.tile);
      spots.sort((a, b) => a.idx - b.idx);
    } else if (c.P) spots = Array.from({ length: n }, (_, i) => { const f = n === 1 ? 0.5 : i / (n - 1); return { x: W * (0.5 + [-1, 0, 1, 0][i % 4] * 0.26), y: Hh * (0.9 - 0.22 * f), size: 135 * k, tile: tiles[i] }; });
    else spots = roadPoints(n).map(([x, y], i) => ({ x: x * k + ox, y: y * k, size: (118 - i * 3) * k, tile: tiles[i] }));
    const svg = L.svg("svg", { width: W, height: Hh }, root); svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible";
    if (spots.length > 1) {
      const pts = spots.map((q) => [q.x, q.y]);
      const Q = c.P ? [[W * 0.1, Hh * 0.99], ...pts, [W * 0.95, Hh * 0.52]] : [[470 * k + ox, 790 * k], ...pts, [1330 * k + ox, 30 * k]];
      let d = `M${Q[0][0]} ${Q[0][1]}`;
      for (let i = 0; i < Q.length - 1; i++) {
        const p0 = Q[Math.max(i - 1, 0)], p1 = Q[i], p2 = Q[i + 1], p3 = Q[Math.min(i + 2, Q.length - 1)];
        d += ` C${p1[0] + (p2[0] - p0[0]) / 6} ${p1[1] + (p2[1] - p0[1]) / 6},${p2[0] - (p3[0] - p1[0]) / 6} ${p2[1] - (p3[1] - p1[1]) / 6},${p2[0]} ${p2[1]}`;
      }
      const g = L.svg("path", { d, fill: "none", stroke: acc, "stroke-width": 56 * k, opacity: 0.7 }, svg); g.style.filter = `blur(${16 * k}px)`;
      L.svg("path", { d, fill: "none", stroke: "#1a1407", "stroke-width": 46 * k, "stroke-linecap": "round" }, svg);
      L.svg("path", { d, fill: "none", stroke: acc, "stroke-width": 19 * k, "stroke-linecap": "round" }, svg);
    }
    spots.forEach((sp) => {
      const t = sp.tile, size = sp.size, ic = size * 0.6;
      const e = el("div", "abs", root); L.pos(e, sp.x - size / 2, sp.y - size / 2, size, size); e.dataset.tile = "1";
      e.style.cssText += `;border-radius:${size * 0.12}px;overflow:hidden;background:${t.tile || "#16161a"};border:${(pics ? 6 : 4) * k}px solid ${acc};box-shadow:0 ${8 * k}px ${24 * k}px rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center`;
      if (t.src) { const im = el("img", "", e); im.style.cssText = "width:100%;height:100%;object-fit:cover"; L.setImg(im, L.projUrl(t.src)); }
      else e.innerHTML = `<svg viewBox="0 0 24 24" width="${ic}" height="${ic}" role="img" aria-label="${L.esc(t.title || "")}"><path fill="#${t.hex}" d="${t.d}"/></svg>`;
    });
    /* words: a tag chip, a headline whose KEY words are big and together, an audience line */
    const lx = c.P ? s.x : 52 * k + ox, colW = c.P ? s.w : 600 * k;
    let tg = null;
    if (p.tag) {
      tg = el("div", "abs", root, L.esc(p.tag)); L.pos(tg, c.P ? s.x : 58 * k + ox, c.P ? s.y : 52 * k); tg.dataset.grp = "tag"; tg.dataset.block = "tag";
      tg.style.cssText += `;background:${acc};color:${L.isDark(acc) ? "#fff" : "#0b0b0e"};font:900 ${40 * k * (c.P ? 1.3 : 1)}px ${heavyFamily()};letter-spacing:-.01em;padding:${6 * k}px ${20 * k}px ${8 * k}px;border-radius:${12 * k}px;transform:rotate(-1.5deg);white-space:nowrap`;
    }
    const words = String(p.title || c.brand.name || "").split(/\s+/).filter(Boolean);
    const norm = (w) => w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
    let a0 = -1, a1 = -1;
    const want = String(p.accent || "").split(/\s+/).map(norm).filter(Boolean);
    if (want.length && want.some((w) => !STOP.has(w))) for (let i = 0; i + want.length <= words.length; i++) if (want.every((w, j) => norm(words[i + j]) === w)) { a0 = i; a1 = i + want.length; break; }
    if (a0 < 0) { let best = [0, 0, -1]; for (let i = 0; i < words.length; i++) { let j = i, len = 0; while (j < words.length && !STOP.has(norm(words[j])) && j - i < 3) { len += words[j].length; j++; } if (len > best[2]) best = [i, j, len]; } [a0, a1] = best[2] > 0 ? [best[0], best[1]] : [0, Math.min(words.length, 2)]; }
    const head = el("div", "abs", root); L.pos(head, lx, c.P ? s.y + 120 * k : 112 * k, colW); head.dataset.grp = "head";
    head.style.cssText += `;color:${ink};font:900 ${124 * k * (c.P ? 1.55 : 1)}px/.93 ${heavyFamily()};letter-spacing:-.045em;text-transform:uppercase;text-shadow:0 ${6 * k}px ${34 * k}px #000`;
    const line = (txt, big) => `<span class="fv-hl" style="display:block;width:max-content;white-space:nowrap;${big ? `color:${acc};font-size:1.42em;text-shadow:0 0 ${50 * k}px ${L.hexA(acc, 0.35)},0 ${6 * k}px ${30 * k}px #000` : ""}">${L.esc(txt)}</span>`;
    head.innerHTML = (a0 > 0 ? line(words.slice(0, a0).join(" "), false) : "") + (c.P ? line(words.slice(a0, a1).join(" "), true) : words.slice(a0, a1).map((w) => line(w, true)).join("")) + (a1 < words.length ? line(words.slice(a1).join(" "), false) : "");
    const fitHead = () => {
      let px = parseFloat(head.style.fontSize) || 124 * k;
      const wide = () => Math.max(...[...head.querySelectorAll(".fv-hl")].map((e) => e.offsetWidth));
      const low = () => !c.P && head.offsetTop + head.offsetHeight > 0.86 * Hh - 70 * k;   /* never past the bottom: room for the audience line */
      for (let i = 0; i < 60 && px > 40 * k && (wide() > colW || low()); i++) { px *= 0.97; head.style.fontSize = px + "px"; }
    };
    const growHead = () => {                                  /* a short headline grows to fill the left column, like the approved design */
      if (c.P) return;
      let px = parseFloat(head.style.fontSize) || 124 * k;
      const target = Math.min(0.56 * Hh, 0.86 * Hh - 96 * k) - parseFloat(head.style.top);        /* room is kept below for the audience line */
      const wide = () => Math.max(...[...head.querySelectorAll(".fv-hl")].map((e) => e.offsetWidth));
      for (let i = 0; i < 40 && head.offsetHeight < target * 0.9 && wide() < colW * 0.96 && px < 210 * k; i++) { px *= 1.04; head.style.fontSize = px + "px"; }
      fitHead();
    };
    fitHead(); growHead(); fits.push(fitHead, growHead);
    const subTxt = String(p.sub || "");
    let subEl = null;
    if (subTxt) {
      subEl = el("div", "abs", root, subTxt.split(/\s+/).map((w) => /^\*.*\*[.,!?]*$/.test(w) ? `<i style="font-style:normal;color:${acc}">${L.esc(w.replace(/\*/g, ""))}</i>` : L.esc(w)).join(" "));
      subEl.dataset.grp = "sub";
      L.pos(subEl, lx + 6 * k, 536 * k);
      subEl.style.cssText += `;color:#fff;font:800 ${44 * k * (c.P ? 1.3 : 1)}px ${heavyFamily()};letter-spacing:-.02em;text-transform:uppercase;white-space:nowrap;text-shadow:0 ${4 * k}px ${20 * k}px #000`;
      const fitSub = () => { let px = parseFloat(subEl.style.fontSize) || 44 * k; for (let i = 0; i < 40 && px > 24 * k && subEl.offsetWidth > colW - 6 * k; i++) { px *= 0.96; subEl.style.fontSize = px + "px"; } };
      fitSub(); fits.push(fitSub);
    }
    const place = () => {
      if (tg) head.style.top = Math.max(parseFloat(head.style.top), tg.offsetTop + tg.offsetHeight + 12 * k) + "px";
      if (subEl) subEl.style.top = (c.P && pics ? Math.max(Hh * 0.885, head.offsetTop + head.offsetHeight + 22 * k) : head.offsetTop + head.offsetHeight + 26 * k) + "px";
    };
    place();
    fits.push(place);
    return {};
  }

  /* ------------------------------------------------------------ insider */
  /* The light kinetic-explainer cover (theme insider-light): an off-white canvas with a faint grid, ONE hero visual on top
     (9:16) or on the left (16:9), and below / beside it a centred mixed-weight stack: a small regular lead line, ONE huge
     black keyword line, an optional medium line, and a final line in a black box with white bold type, slightly turned.
     2 to 4 accent asterisks are scattered (some large and half off the frame), never over the words.
     params: lead, title (the huge keyword: 1-3 words), mid, chip, handle,
             hero {src, kind: cutout|card, color (keep colour), ar (card)} | tiles [{d, hex, title} | {src}] (the network hero),
             bursts (2-4, default 3). "*word*" in lead or mid sets that word bold. */
  const INK = "#0e0e10";
  function asterisk(parent, r, color, seed) {
    /* an asterisk with rounded arms of uneven length: deterministic from seed */
    const svg = L.svg("svg", { width: r * 2, height: r * 2, viewBox: `${-r} ${-r} ${r * 2} ${r * 2}` }, parent);
    svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible";
    const n = 11 + (seed % 3), w = r * 0.2;
    for (let i = 0; i < n; i++) {
      const a = (360 / n) * i + (seed * 37) % 30, len = r * (0.78 + 0.22 * Math.abs(Math.sin((i + 1) * (seed + 3) * 1.7)));
      L.svg("line", { x1: 0, y1: 0, x2: len - w / 2, y2: 0, stroke: color, "stroke-width": w, "stroke-linecap": "round", transform: `rotate(${a.toFixed(2)})` }, svg);
    }
    return svg;
  }
  const richLine = (txt) => String(txt).split(/\s+/).filter(Boolean).map((w) => /^\*.+\*[.,!?:;]*$/.test(w) ? `<b style="font-weight:800;color:${INK}">${L.esc(w.replace(/\*/g, ""))}</b>` : L.esc(w)).join(" ");
  const overlaps = (a, b, m = 0) => a.x < b.x + b.w + m && a.x + a.w > b.x - m && a.y < b.y + b.h + m && a.y + a.h > b.y - m;

  function insider(root, c) {
    const p = c.p, W = c.W, Hh = c.H, s = c.safe, P = c.P, u = P ? W / 1080 : Hh / 720;
    const acc = C.accent, bgc = L.isDark(C.bg) ? "#f2f2f2" : C.bg, FONT = "'Inter', var(--sans)";
    const bg = el("div", "abs", root); L.pos(bg, 0, 0, W, Hh);
    bg.style.background = `radial-gradient(ellipse 80% 60% at 50% ${P ? 30 : 50}%, #fbfbfb 0%, ${bgc} 70%)`;
    const grid = el("div", "abs", root); L.pos(grid, 0, 0, W, Hh);
    grid.style.cssText += `;background-image:linear-gradient(rgba(0,0,0,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(0,0,0,.035) 1px,transparent 1px);background-size:${72 * u}px ${72 * u}px;background-position:${W / 2}px 0`;
    const bl = el("div", "abs", root); L.pos(bl, 0, 0, W, Hh);              /* the scattered asterisks, under everything else */
    /* zones */
    const hz = P ? { x: s.x, y: s.y + s.h * 0.04, w: s.w, h: s.h * 0.6 } : { x: s.x, y: s.y + s.h * 0.04, w: s.w * 0.46, h: s.h * 0.92 };
    const tz = P ? { x: s.x, y: s.y + s.h * 0.67, w: s.w, h: s.h * 0.33 } : { x: s.x + s.w * 0.49, y: s.y, w: s.w * 0.51, h: Math.min(s.h, 0.84 * Hh - s.y) };
    const heroRects = [];
    /* ---- hero */
    const hero = p.hero || {};
    const tiles = (p.tiles || []).slice(0, 7);
    const shadow = (a = 0.22) => `0 ${14 * u}px ${34 * u}px rgba(15,15,20,${a}), 0 ${3 * u}px ${8 * u}px rgba(15,15,20,.08)`;
    if (tiles.length >= 2) {
      /* network: round white tiles in rows of two on either side of a dashed trunk, an odd last one centred under it */
      /* 9:16: the network may use the whole upper part, above the safe top too (no words go there) */
      const nz = P ? { x: hz.x, y: Hh * 0.05, w: hz.w, h: tz.y - 40 * u - Hh * 0.05 } : hz;
      const n = tiles.length, rows = Math.ceil(n / 2), pitch = Math.min(nz.h / rows, nz.w * 0.42), d = Math.min(pitch * 0.84, (P ? 240 : 150) * u);
      const cx = nz.x + nz.w / 2, dx = Math.min(nz.w * 0.26, d * 1.1), y0 = nz.y + (nz.h - pitch * rows) / 2 + pitch / 2;
      const spots = tiles.map((t, i) => { const r = Math.floor(i / 2), last = n % 2 === 1 && i === n - 1; return { t, x: last ? cx : cx + (i % 2 ? dx : -dx), y: y0 + r * pitch }; });
      const svg = L.svg("svg", { width: W, height: Hh }, root); svg.style.cssText = "position:absolute;left:0;top:0;overflow:visible";
      const line = (x1, y1, x2, y2) => L.svg("line", { x1, y1, x2, y2, stroke: "#a9a9ae", "stroke-width": 2.2 * u, "stroke-dasharray": `${7 * u} ${6 * u}` }, svg);
      const yEnd = spots[n - 1].x === cx ? spots[n - 1].y - d / 2 : spots[n - 1].y;
      line(cx, spots[0].y, cx, yEnd);
      spots.forEach((q) => { if (q.x !== cx) line(q.x + (q.x < cx ? d / 2 : -d / 2), q.y, cx, q.y); });
      spots.forEach((q) => {
        const e = el("div", "abs", root); L.pos(e, q.x - d / 2, q.y - d / 2, d, d); e.dataset.tile = "1";
        e.style.cssText += `;border-radius:50%;background:#fff;box-shadow:${shadow(0.2)};display:flex;align-items:center;justify-content:center;overflow:hidden`;
        const ic = d * 0.5, t = q.t;
        if (t.src) { const im = el("img", "", e); im.style.cssText = `width:${ic}px;height:${ic}px;object-fit:contain`; L.setImg(im, L.projUrl(t.src)); }
        else { const hex = String(t.hex || "0e0e10").replace("#", ""), light = !L.isDark("#" + hex) && parseInt(hex.slice(0, 2), 16) * 0.299 + parseInt(hex.slice(2, 4), 16) * 0.587 + parseInt(hex.slice(4, 6), 16) * 0.114 > 200;
          e.innerHTML = `<svg viewBox="0 0 24 24" width="${ic}" height="${ic}" role="img" aria-label="${L.esc(t.title || "")}"><path fill="${light ? INK : "#" + hex}" d="${t.d}"/></svg>`; }
        heroRects.push({ x: q.x - d / 2, y: q.y - d / 2, w: d, h: d });
      });
    } else if (hero.src && (hero.kind || (isCut(hero.src, p) ? "cutout" : "card")) === "cutout") {
      /* a cut-out over a big accent asterisk */
      const url = L.projUrl(hero.src), info = L.cutInfo(url), asp = info ? (info.h * info.nh) / (info.w * info.nw) : 1.2;
      let h = hz.h, w = h / asp; if (w > hz.w * 0.82) { w = hz.w * 0.82; h = w * asp; }
      const x = hz.x + (hz.w - w) / 2, y = hz.y + hz.h - h;
      const r = Math.min(hz.w * 0.48, h * 0.62), sh = el("div", "abs", root);
      L.pos(sh, x + w * 0.5 - r + (P ? w * 0.08 : 0), y + h * 0.42 - r, r * 2, r * 2);
      asterisk(sh, r, acc, 5); sh.style.filter = `drop-shadow(0 ${16 * u}px ${20 * u}px rgba(15,15,20,.18))`;
      const node = el("div", "abs", root); L.pos(node, x, y, w, h); node.dataset.tile = "1";
      const img = el("img", "", node);
      if (info) { const iw = w / info.w, ih = h / info.h; img.style.cssText = `position:absolute;left:${-info.x * iw}px;top:${-info.y * ih}px;width:${iw}px;height:${ih}px;max-width:none`; }
      else img.style.cssText = "position:absolute;inset:0;width:100%;height:100%;object-fit:contain";
      node.style.filter = `${hero.color ? "" : "grayscale(1) contrast(1.12) "}drop-shadow(${5 * u}px 0 0 #fff) drop-shadow(-${5 * u}px 0 0 #fff) drop-shadow(0 ${5 * u}px 0 #fff) drop-shadow(0 -${5 * u}px 0 #fff) drop-shadow(${10 * u}px ${18 * u}px ${22 * u}px rgba(15,15,20,.35))`;
      L.setImg(img, url);
      heroRects.push({ x, y, w, h });
    } else if (hero.src) {
      /* a rounded, shadowed card holding a picture */
      const ar = +hero.ar || 1.6;
      let w = hz.w * (P ? 0.86 : 0.92), h = w / ar; if (h > hz.h * 0.86) { h = hz.h * 0.86; w = h * ar; }
      const x = hz.x + (hz.w - w) / 2, y = hz.y + (hz.h - h) / 2 + (P ? hz.h * 0.06 : 0);
      const cd = el("div", "abs", root); L.pos(cd, x, y, w, h); cd.dataset.tile = "1";
      cd.style.cssText += `;border-radius:${26 * u}px;overflow:hidden;background:#fff;border:${6 * u}px solid #fff;box-shadow:${shadow(0.3)};transform:rotate(${P ? -1.5 : -2}deg)`;
      const im = el("img", "", cd); im.style.cssText = `width:100%;height:100%;object-fit:cover;border-radius:${20 * u}px`; L.setImg(im, L.projUrl(hero.src));
      heroRects.push({ x, y, w, h });
    }
    /* ---- the text stack */
    const st = el("div", "abs", root); L.pos(st, tz.x, tz.y, tz.w);
    st.style.cssText += `;display:flex;flex-direction:column;align-items:center;text-align:center;font-family:${FONT};color:${INK}`;
    const row = (grp, html, css) => { const e = el("div", "", st, html); e.dataset.grp = grp; e.style.cssText += `;white-space:nowrap;${css}`; return e; };
    const lead = p.lead ? row("lead", richLine(p.lead), `font-weight:400;font-size:${66 * u}px;line-height:1.08;letter-spacing:-.02em;color:#2b2b30`) : null;
    const tw = String(p.title || "").split(/\s+/).filter(Boolean);
    const title = tw.length ? row("title", "", `font-weight:800;font-size:${(P ? 250 : 150) * u}px;line-height:.98;letter-spacing:-.045em;color:${INK}`) : null;
    const mid = p.mid ? row("mid", richLine(p.mid), `font-weight:500;font-size:${64 * u}px;line-height:1.1;letter-spacing:-.02em;color:#2b2b30`) : null;
    let chip = null, chipT = null;
    if (p.chip) {
      chip = el("div", "", st); chip.dataset.block = "chip";
      chip.style.cssText += `;margin-top:${18 * u}px;background:${INK};border-radius:${14 * u}px;padding:${8 * u}px ${30 * u}px ${12 * u}px;transform:rotate(-2deg);box-shadow:0 ${14 * u}px ${30 * u}px rgba(15,15,20,.3)`;
      chipT = el("div", "", chip, L.esc(p.chip)); chipT.dataset.grp = "chip";
      chipT.style.cssText += `;white-space:nowrap;font:800 ${84 * u}px/1.12 ${FONT};letter-spacing:-.02em;color:#fff`;
    }
    const lim = tz.w * 0.96;
    const shrink = (e, max, min) => { let px = max; e.style.fontSize = px + "px"; for (let i = 0; i < 60 && px > min && e.scrollWidth > lim; i++) { px *= 0.97; e.style.fontSize = px + "px"; } return px; };
    const handle = p.handle ? el("div", "abs", root, L.esc(p.handle)) : null;
    if (handle) { handle.dataset.free = "1"; handle.style.cssText += `;font:700 ${(P ? 46 : 26) * u}px ${FONT};color:rgba(14,14,16,.2);white-space:nowrap`; }
    const bursts = [];
    const run = () => {
      const k0 = 1;
      let scale = k0;
      for (let pass = 0; pass < 12; pass++) {
        if (lead) shrink(lead, 66 * u * scale, 30 * u);
        if (title) {
          const max = (P ? 250 : 150) * u * scale;
          title.innerHTML = L.esc(tw.join(" "));
          let px = shrink(title, max, 60 * u);
          if (tw.length >= 3 && px < max * 0.72) {                       /* a long keyword line breaks in two, both lines as big as they can be */
            let best = 1, bd = 1e9; for (let i = 1; i < tw.length; i++) { const dd = Math.abs(tw.slice(0, i).join(" ").length - tw.slice(i).join(" ").length); if (dd < bd) { bd = dd; best = i; } }
            title.innerHTML = `${L.esc(tw.slice(0, best).join(" "))}<br>${L.esc(tw.slice(best).join(" "))}`;
            px = shrink(title, max, 60 * u);
          }
        }
        if (mid) shrink(mid, 64 * u * scale, 30 * u);
        if (chipT) { let px = 84 * u * scale; chipT.style.fontSize = px + "px"; for (let i = 0; i < 60 && px > 30 * u && chip.offsetWidth > lim; i++) { px *= 0.97; chipT.style.fontSize = px + "px"; } }
        if (st.offsetHeight <= tz.h) break;
        scale *= 0.92;
      }
      st.style.top = (P ? tz.y : tz.y + (tz.h - st.offsetHeight) / 2) + "px";
      if (handle) { if (P) L.pos(handle, W / 2 - handle.offsetWidth / 2, Math.min(Hh - s.y * 0.6, st.offsetTop + st.offsetHeight + 90 * u)); else L.pos(handle, s.x, s.y + s.h - handle.offsetHeight); }
      /* asterisks: candidate spots, kept only when clear of every word (with a margin) */
      bl.innerHTML = ""; bursts.length = 0;
      const words = { x: st.offsetLeft, y: st.offsetTop, w: st.offsetWidth, h: st.offsetHeight };
      const cand = P
        ? [[W * 0.97, Hh * 0.93, 280], [W * 0.07, Hh * 0.07, 120], [W * 0.92, Hh * 0.46, 72], [W * 0.06, Hh * 0.6, 64], [W * 1.0, Hh * 1.0, 250]]
        : [[W * 0.04, Hh * 0.98, 170], [W * 0.98, Hh * 0.04, 120], [W * 0.5, Hh * 0.12, 46], [W * 0.47, Hh * 0.86, 40]];
      const want = Math.max(2, Math.min(4, +p.bursts || 3)) - (hero.kind === "cutout" || (hero.src && isCut(hero.src, p) && !hero.kind) ? 1 : 0);
      for (const [x, y, r0] of cand) {
        if (bursts.length >= want) break;
        const r = r0 * u, b = { x: x - r, y: y - r, w: 2 * r, h: 2 * r };
        if (overlaps(b, words, 24 * u) || (handle && overlaps(b, { x: handle.offsetLeft, y: handle.offsetTop, w: handle.offsetWidth, h: handle.offsetHeight }, 8 * u))) continue;
        if (!P && x - r < W * 0.84 && x + r > W * 0.84 && y + r > Hh * 0.86) continue;            /* the duration stamp corner */
        if (!P && x > W * 0.8 && y > Hh * 0.8) continue;
        if (heroRects.some((h) => overlaps(b, h, -Math.min(h.w, h.h) * 0.3))) continue;          /* a little behind a hero edge is fine, not across it */
        const e = el("div", "abs", bl); L.pos(e, b.x, b.y, b.w, b.h); asterisk(e, r, acc, bursts.length + 1);
        if (r0 > 100) e.style.opacity = ".95";
        bursts.push(b);
      }
    };
    run(); fits.push(run);
    return {};
  }

  const LAYOUTS = { subject, number, split, caption, frame, road, insider };
  S.thumbnail = {
    build(root, c) {
      const f = LAYOUTS[String((c.p || {}).layout || "")];
      return f ? f(root, c) : base.build(root, c);
    },
    update(st, t, c) { if (LAYOUTS[String((c.p || {}).layout || "")]) { for (const f of fits.splice(0)) f(); } else if (base.update) base.update(st, t, c); },
    cues: () => [],
  };
})();
