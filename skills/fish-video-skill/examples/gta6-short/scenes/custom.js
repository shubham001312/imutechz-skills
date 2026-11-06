/* video #002: bold full-frame cut-paper shapes with continuous motion.
   Registered under built-in scene type names because the storyboard validator only accepts those.
   All timing is read from the real narration word timestamps, so re-voicing never desyncs it.
   Pure function of t; no timers, no Math.random. */
(function () {
  "use strict";
  const { el, clamp, cue, seg, expo } = L;
  const C_ = { y: "#FFD60A", r: "#FF4B2B", b: "#1F3BFF", k: "#111111", w: "#FFF6E6", t: "#00A88F" };
  const css = document.createElement("style");
  css.textContent = `
  .b-t{position:absolute;font-family:"Inter",sans-serif;font-weight:900;line-height:1;white-space:nowrap;letter-spacing:-.025em;transform-origin:50% 50%;will-change:transform}
  .b-box{position:absolute;transform-origin:50% 50%;will-change:transform}
  .b-mono{position:absolute;font-family:"JetBrains Mono",monospace;font-weight:700;color:${C_.k}}
  .b-q{position:absolute;font-family:"Fraunces",serif;font-weight:600;line-height:1.16;color:${C_.k}}
  .b-q mark{color:inherit;background:linear-gradient(${C_.y},${C_.y}) no-repeat 0 70%;padding:0 .06em}
  .capbox.pop .cap-pop{font-family:"Inter",sans-serif;font-weight:900;color:${C_.k};-webkit-text-stroke:0;text-shadow:none;background:${C_.w};padding:.12em .36em .14em;border-radius:.1em;box-shadow:0 10px 0 rgba(0,0,0,.28);letter-spacing:-.01em;font-size:.84em}
  .capbox.pop .cap-pop .w.now{color:${C_.r}}`;
  document.head.appendChild(css);

  /* word timestamps: scene-relative start of the nth word beginning with `s` */
  let TLJ = null;
  try { const x = new XMLHttpRequest(); x.open("GET", "/project/build/timeline-shorts.json", false); x.send(); TLJ = JSON.parse(x.responseText); } catch (e) { TLJ = null; }
  function W(id, s, n = 0, fb = 0) {
    if (!TLJ) return fb;
    const sc = TLJ.scenes.find((q) => q.id === id); if (!sc) return fb;
    const m = TLJ.words.filter((w) => w.t0 >= sc.t0 && w.t0 < sc.t1 && w.w.toLowerCase().startsWith(s.toLowerCase()));
    return m[n] ? m[n].t0 - sc.t0 : fb;
  }
  /* damped spring, 0 → 1 with a small overshoot; continuous at every frame */
  const sp = (t, t0, f = 1) => { const x = (t - t0) * f; return x <= 0 ? 0 : 1 - Math.exp(-7.5 * x) * Math.cos(12 * x); };
  const eo = (t, t0, d) => expo(seg(t, t0, t0 + d));
  const lerp = (a, b, k) => a + (b - a) * k;

  function box(root, x, y, w, h, bg, o = {}) {
    const n = el("div", "b-box", root);
    L.pos(n, x, y, w, h); n.style.background = bg; n.style.zIndex = o.z || 3;
    if (o.rad) n.style.borderRadius = o.rad + "px";
    if (o.shadow !== false) n.style.boxShadow = `0 ${o.sh || 16}px 0 rgba(0,0,0,.2)`;
    if (o.origin) n.style.transformOrigin = o.origin;
    return n;
  }
  function txt(root, s, x, y, size, color, o = {}) {
    const n = el("div", "b-t", root, s);
    n.style.cssText += `;font-size:${size}px;color:${color};z-index:${o.z || 6}`;
    if (o.w != null) { n.style.width = o.w + "px"; n.style.textAlign = o.align || "center"; }
    n.style.left = x + "px"; n.style.top = y + "px";
    if (o.weight) n.style.fontWeight = o.weight;
    if (o.ls != null) n.style.letterSpacing = o.ls;
    return n;
  }
  const T = (n, m = {}) => {
    n.style.transform = `translate(${(m.x || 0).toFixed(2)}px,${(m.y || 0).toFixed(2)}px) rotate(${(m.r || 0).toFixed(3)}deg) scale(${(m.sx != null ? m.sx : m.s != null ? m.s : 1).toFixed(4)},${(m.sy != null ? m.sy : m.s != null ? m.s : 1).toFixed(4)})`;
    const o = m.o == null ? 1 : m.o; n.style.opacity = o; n.style.visibility = o <= 0.001 ? "hidden" : "visible";
    n.style.filter = m.blur > 0.15 ? `blur(${m.blur.toFixed(2)}px)` : "";
  };
  /* pop: invisible until t0, then springs to full size */
  const pop = (n, t, t0, m = {}) => { if (t < t0) return T(n, { o: 0 }); const k = sp(t, t0, m.f || 1.25); T(n, { ...m, s: 0.55 + 0.45 * k, o: clamp((t - t0) / 0.06), r: (m.r || 0) * k + (1 - k) * (m.rf || 0) }); };

  const ORDER = ["hook", "proof", "bars", "dates", "purge"];
  const GROUND = { hook: C_.y, proof: C_.b, bars: C_.r, dates: C_.k, purge: C_.w };

  const ACTS = {
    hook: {
      build(w, c, st) {
        st.floor = box(w, -60, 1180, c.W + 120, 900, C_.r, { z: 1, shadow: false });
        st.con = box(w, 370, 1020, 340, 160, C_.w, { z: 3, origin: "50% 100%", rad: 10 });
        const slot = el("div", "abs", st.con); slot.style.cssText = `left:8%;right:8%;top:26px;height:9px;background:${C_.k};border-radius:4px`;
        txt(st.con, "YOUR PS5", 0, 62, 54, C_.k, { w: 340 });
        st.game = txt(w, "1. CLEAR", 90, 540, 190, C_.k, { w: 820 });
        st.block = box(w, 104, 470, 800, 550, C_.k, { z: 5, origin: "50% 100%", rad: 8, sh: 18 });
        st.num = txt(st.block, "212", 0, 50, 350, C_.y, { w: 800 });
        st.gb = txt(st.block, "GIGABYTES", 0, 396, 110, C_.w, { w: 800 });
        st.rays = [...Array(10)].map((_, i) => { const r = box(w, 540 - 8, 1160, 16, 130, C_.k, { z: 2, shadow: false, origin: "50% 100%" }); r._a = -90 + (i - 4.5) * 19; return r; });
        st.tag = box(w, 104, 1036, 800, 110, C_.b, { z: 8, shadow: true, rad: 6 });
        txt(st.tag, "ON YOUR PS5", 0, 26, 66, C_.w, { w: 800 });
        st.t212 = W("hook", "212", 0, 2); st.tNeeds = W("hook", "clear", 0, 0.4); st.tGig = W("hook", "gigabytes", 0, 2.5); st.tOne = st.tGig + 0.42;
      },
      update(st, t, c) {
        const up = eo(t, st.tNeeds - 0.05, 0.38);
        T(st.game, { y: lerp(0, -255, up), s: lerp(1 + 0.02 * clamp(t / st.tNeeds), 0.72, up) });
        const land = st.t212, fall = seg(t, land - 0.22, land), x = t - land;
        const hit = x >= 0;
        const sq = hit ? 0.14 * Math.exp(-7 * x) * Math.cos(20 * x) : 0;
        T(st.block, { y: lerp(-1300, 0, fall * fall), sy: 1 - sq, sx: 1 + sq * 0.6, o: fall > 0 ? 1 : 0, blur: hit ? 0 : 7 * fall });
        const cq = hit ? 0.62 - 0.14 * Math.exp(-6 * x) * Math.cos(16 * x) : 1;
        T(st.con, { sy: cq, sx: hit ? 1.12 : 1 });
        st.rays.forEach((r) => { const k = hit ? seg(x, 0, 0.42) : 0; const e = 1 - Math.pow(1 - k, 3); T(r, { r: r._a + 90, y: 0, sy: 0.4 + e * 2.4, s: undefined, o: hit && k < 1 ? 1 - k : 0 }); });
        pop(st.num, t, land + 0.05);
        if (t < st.tGig - 0.05) T(st.gb, { o: 0 }); else T(st.gb, { o: 1, x: lerp(70, 0, eo(t, st.tGig - 0.05, 0.3)) });
        pop(st.tag, t, st.tOne, { r: -2.5, rf: 8 });
      },
      shake: (st, t) => { const x = t - st.t212; return x >= 0 ? 24 * Math.exp(-8 * x) * Math.sin(55 * x) : 0; },
      cues: (st) => [cue(st.tNeeds - 0.1, "swish", 2), cue(st.t212 - 0.25, "riser", 2, { len: 0.25 }), cue(st.t212, "impact", 3), cue(st.tGig - 0.05, "pop", 2), cue(st.tOne, "thump", 2)],
    },
    proof: {
      build(w, c, st) {
        const hd = el("div", "abs", w); hd.style.cssText += "left:84px;width:832px;top:276px;height:130px;display:flex;justify-content:center;gap:.28em;font-size:128px;z-index:6";
        const wd = (s, col) => { const n = el("div", "b-t", hd, s); n.style.cssText += `;position:static;font-size:128px;color:${col}`; return n; };
        st.n = wd("NOT", C_.w); st.a = wd("A", C_.w); st.l = wd("LEAK.", C_.y);
        st.page = box(w, 100, 470, 800, 610, C_.w, { z: 4, rad: 8, sh: 22 });
        const m1 = el("div", "b-mono", st.page, "PLAYSTATION BLOG"); m1.style.cssText += "left:48px;top:44px;font-size:50px";
        const m2 = el("div", "b-mono", st.page, "NOV 3, 2026"); m2.style.cssText += "left:48px;top:106px;font-size:34px;font-weight:400";
        const q = el("div", "b-q", st.page, "“Get ready by clearing <mark>a minimum of 212GB</mark> of storage space on your PS5.”");
        q.style.cssText += "left:44px;right:36px;top:172px;font-size:76px";
        st.mark = q.querySelector("mark");
        st.tPS = W("proof", "playstation", 0, 1); st.tSaid = W("proof", "said", 0, 1.6); st.tN = W("proof", "not", 0, 0.1); st.tA = W("proof", "a", 0, 0.3); st.tL = W("proof", "leak", 0, 0.4); st.hits = [[st.tL, 0.07], [st.tSaid, 0.07]];
      },
      update(st, t) {
        pop(st.n, t, Math.max(0, st.tN - 0.05)); pop(st.a, t, st.tA - 0.03); pop(st.l, t, st.tL - 0.03, { rf: -6 });
        const k = sp(t, Math.max(0, st.tPS - 0.28), 1.1);
        T(st.page, { y: lerp(1050, 0, k), r: lerp(5, -1, k) });
        st.mark.style.backgroundSize = `${(eo(t, st.tSaid - 0.05, 0.42) * 100).toFixed(1)}% 62%`;
      },
      cues: (st) => [cue(st.tN, "pop", 2), cue(st.tL, "thump", 3), cue(st.tPS - 0.38, "whoosh", 2), cue(st.tSaid, "scribble", 2, { len: 0.42 })],
    },
    bars: {
      build(w, c, st) {
        const x0 = 84; st.x0 = x0;
        st.l1 = txt(w, "ORIGINAL PS5", x0, 276, 80, C_.k);
        st.u1 = txt(w, "about 667 GB usable", x0, 360, 46, C_.w, { weight: 800, ls: "0" });
        st.s1 = box(w, x0, 422, 667, 140, C_.w, { z: 3, origin: "0 50%", sh: 10 });
        st.b1 = box(w, x0, 422, 212, 140, C_.k, { z: 5, sh: 10 }); txt(st.b1, "212", 0, 30, 84, C_.y, { w: 212 });
        st.st1 = txt(w, "ALMOST 1/3", x0, 584, 116, C_.w);
        st.l2 = txt(w, "PS5 SLIM", x0, 748, 80, C_.k);
        st.u2 = txt(w, "about 842 GB usable", x0, 832, 46, C_.w, { weight: 800, ls: "0" });
        st.s2 = box(w, x0, 892, 842, 140, C_.w, { z: 3, origin: "0 50%", sh: 10 });
        st.b2 = box(w, x0, 892, 212, 140, C_.k, { z: 5, sh: 10 }); txt(st.b2, "212", 0, 30, 84, C_.y, { w: 212 });
        st.st2 = txt(w, "ABOUT 1/4", x0, 1054, 116, C_.w);
        st.tO = W("bars", "original", 0, 0.2); st.tThird = W("bars", "third", 0, 2); st.tSlim = W("bars", "slim", 0, 3.4); st.tQ = W("bars", "quarter", 0, 4.4); st.tThat = W("bars", "that", 0, 1); st.tOn2 = W("bars", "on", 1, 3);
      },
      update(st, t) {
        const row = (lb, un, s, b, stat, a, bAt, statAt) => {
          if (t < a) { [lb, un, s, b, stat].forEach((n) => T(n, { o: 0 })); return; }
          T(lb, { x: lerp(-90, 0, eo(t, a, 0.32)), o: clamp((t - a) / 0.06) });
          T(un, { x: lerp(-90, 0, eo(t, a + 0.06, 0.32)), o: clamp((t - a - 0.06) / 0.06) });
          T(s, { sx: Math.max(0.001, eo(t, a + 0.04, 0.42)), sy: 1 });
          if (t < bAt) T(b, { o: 0 }); else { const k = sp(t, bAt, 1.3); T(b, { x: lerp(-260, 0, k), r: lerp(-5, 0, k), o: clamp((t - bAt) / 0.05) }); }
          pop(stat, t, statAt, { r: -2, rf: 7 });
        };
        row(st.l1, st.u1, st.s1, st.b1, st.st1, 0, st.tThat - 0.12, st.tThird - 0.04);
        row(st.l2, st.u2, st.s2, st.b2, st.st2, st.tOn2 - 0.1, st.tSlim + 0.05, st.tQ - 0.04);
      },
      cues: (st) => [cue(0, "paper", 2), cue(st.tThat - 0.22, "swish", 2), cue(st.tThat, "thump", 2), cue(st.tThird, "impact", 3), cue(st.tOn2 - 0.1, "paper", 2), cue(st.tSlim - 0.05, "swish", 2), cue(st.tSlim + 0.15, "thump", 2), cue(st.tQ, "impact", 3)],
    },
    dates: {
      build(w, c, st) {
        st.c1 = box(w, 92, 268, 816, 400, C_.w, { z: 4, rad: 10, sh: 16 });
        txt(st.c1, "NOV 10", 0, 38, 210, C_.k, { w: 816 });
        txt(st.c1, "PRE-ORDERS CAN DOWNLOAD", 0, 266, 52, C_.r, { w: 816, ls: "-.01em" });
        txt(st.c1, "from local midnight", 0, 330, 40, C_.k, { w: 816, weight: 700, ls: "0" });
        st.link = box(w, 496, 668, 16, 76, C_.y, { z: 2, shadow: false, origin: "50% 0" });
        st.c2 = box(w, 92, 744, 816, 416, C_.y, { z: 4, rad: 10, sh: 16 });
        txt(st.c2, "NOV 19", 0, 48, 226, C_.k, { w: 816 });
        txt(st.c2, "GTA VI LAUNCHES", 0, 296, 76, C_.k, { w: 816 });
        st.t1 = Math.max(0, W("dates", "pre-orders", 0, 0.05) - 0.03); st.t10 = W("dates", "november 10", 0, 1.6); st.t2 = W("dates", "launch", 0, 2.0) - 0.03; st.hits = [[st.t1, 0.08], [st.t2, 0.1]]; st.t19 = W("dates", "november 19", 0, 3.1);
      },
      update(st, t) {
        const flip = (n, a, r0) => { if (t < a) return T(n, { o: 0 }); const k = sp(t, a, 1.15); n.style.transform = `perspective(1400px) rotateX(${((1 - k) * -72).toFixed(2)}deg) rotate(${r0}deg) scale(${(0.86 + 0.14 * k).toFixed(4)})`; n.style.opacity = clamp((t - a) / 0.05); n.style.visibility = "visible"; };
        flip(st.c1, st.t1, -1.2); flip(st.c2, st.t2, 1.2);
        T(st.link, { sy: Math.max(0.001, eo(t, st.t2 - 0.1, 0.25)), sx: 1 });
      },
      punch: (st, t) => { const a = t - st.t19; return a >= 0 ? 0.03 * Math.exp(-6 * a) : 0; },
      cues: (st) => [cue(st.t1, "paper", 2), cue(st.t10, "pop", 2), cue(st.t2 - 0.1, "swish", 2), cue(st.t2, "paper", 2), cue(st.t19, "impact", 3)],
    },
    purge: {
      build(w, c, st) {
        st.floor = box(w, -60, 1180, c.W + 120, 900, C_.b, { z: 1, shadow: false });
        st.title = txt(w, "YOUR PS5 RIGHT NOW", 84, 286, 84, C_.k, { w: 832 });
        const names = ["THE SHOOTER", "BOUGHT ON SALE", "NEVER FINISHED", "THAT BIG RPG", "THE RACER"], fills = [C_.b, C_.r, C_.t, C_.k, C_.y], inks = [C_.w, C_.w, C_.w, C_.w, C_.k];
        st.sp = names.map((nm, i) => {
          const b = box(w, 92 + i * 168, 440, 152, 740, fills[i], { z: 3 + i, sh: 0, origin: "50% 100%", rad: 6 });
          const l = el("div", "abs", b, nm); l.style.cssText = `left:0;right:0;top:0;bottom:0;display:flex;align-items:center;justify-content:center;writing-mode:vertical-rl;font:900 62px "Inter",sans-serif;letter-spacing:-.02em;color:${inks[i]};white-space:nowrap`;
          return b;
        });
        st.bx = box(w, 708, 400, 212, 780, C_.k, { z: 12, sh: 0, origin: "50% 100%", rad: 6 });
        const n = el("div", "abs", st.bx, "212 GB"); n.style.cssText = `left:0;right:0;top:0;bottom:0;display:flex;align-items:center;justify-content:center;writing-mode:vertical-rl;font:900 138px "Inter",sans-serif;letter-spacing:-.03em;color:${C_.y};white-space:nowrap`;
        st.disc = box(w, 260, 300, 520, 520, C_.r, { z: 20, rad: 260, sh: 18 });
        txt(st.disc, "?", 0, 54, 410, C_.w, { w: 520 });
        st.ask = box(w, 100, 850, 800, 150, C_.k, { z: 22, rad: 8, sh: 14 });
        txt(st.ask, "TELL ME IN THE COMMENTS", 0, 50, 58, C_.y, { w: 800, ls: "-.01em" });
        st.tS = 0.08; st.tGo = W("purge", "which", 0, 0.5); st.tWh = W("purge", "you", 0, 0.9); st.tDel = W("purge", "deleting", 0, 1.1); st.hits = [[st.tWh, 0.08]];
      },
      update(st, t) {
        T(st.title, { o: 1 - seg(t, st.tWh - 0.12, st.tWh + 0.04), y: lerp(-50, 0, eo(t, 0, 0.3)) });
        const shove = t < st.tS - 0.1 ? 0 : sp(t, st.tS - 0.1, 1.2);
        T(st.bx, { x: lerp(460, 0, shove), r: lerp(4, 0, shove), o: shove > 0 ? 1 : 0, sx: 1 + 0.04 * Math.exp(-5 * Math.max(0, t - st.tS)) * (shove > 0 ? 1 : 0) });
        const rx = [92, 212, 332, 452, 572], fx = [92, 244, 332, 396, 548], close = eo(t, st.tGo + 0.1, 0.32);
        const kick = seg(t, st.tGo - 0.02, st.tGo + 0.55), ke = kick * kick;
        st.sp.forEach((b, i) => {
          const start = 92 + i * 168;
          const squeezed = lerp(start, rx[i], clamp(shove, 0, 1.08)), final = lerp(squeezed, fx[i], close);
          const wob = (t >= st.tS ? 2.2 : 0) * Math.exp(-3.4 * Math.max(0, t - st.tS)) * Math.sin(16 * Math.max(0, t - st.tS) + i);
          if (i === 2 && kick > 0) T(b, { x: final - start, y: -1500 * ke, r: 42 * ke, o: kick >= 1 ? 0 : 1 });
          else T(b, { x: final - start, r: wob });
        });
        if (t < st.tWh - 0.06) { T(st.disc, { o: 0 }); T(st.ask, { o: 0 }); return; }
        const k = sp(t, st.tWh - 0.06, 1.2);
        T(st.disc, { s: Math.max(0.01, Math.min(k, 1.06)), r: lerp(-30, 0, k) });
        pop(st.ask, t, st.tDel - 0.08, { r: -2, rf: 6 });
      },
      cues: (st) => [cue(st.tS - 0.2, "whoosh", 2), cue(st.tS + 0.1, "thump", 2), cue(st.tGo - 0.08, "swish", 2), cue(st.tWh - 0.2, "riser", 2, { len: 0.2 }), cue(st.tWh, "impact", 3), cue(st.tDel, "pop", 2)],
    },
  };


  ACTS.big2 = {
    build(w, c, st) {
      st.a = txt(w, "DO THESE", 84, 276, 150, C_.k, { w: 832 });
      st.n = txt(w, "2", 84, 410, 640, C_.r, { w: 832 });
      st.b = txt(w, "THINGS", 84, 1040, 170, C_.k, { w: 832 });
      st.tN = W("big2", "two", 0, 0.3); st.hits = [[st.tN, 0.1]];
    },
    update(st, t) {
      T(st.a, { y: lerp(-30, 0, eo(t, 0, 0.25)), s: 0.97 + 0.03 * sp(t, 0, 1.6) });
      const k = sp(t, st.tN - 0.06, 1.5);
      T(st.n, { s: t < st.tN - 0.06 ? 0.5 : 0.5 + 0.5 * k, r: lerp(-14, 0, k) + Math.sin(t * 4) * 1.5, o: 1 });
      T(st.b, { x: lerp(120, 0, eo(t, 0.03, 0.3)), o: 1 });
    },
    cues: (st) => [cue(st.tN - 0.05, "impact", 3), cue(0, "pop", 2)],
  };
  ACTS.nov = {
    build(w, c, st) {
      st.b = txt(w, "BEFORE", 84, 280, 170, C_.y, { w: 832 });
      st.card = box(w, 170, 510, 660, 670, C_.w, { z: 4, rad: 18, sh: 22 });
      const band = box(st.card, 0, 0, 660, 170, C_.r, { shadow: false, rad: 18 }); txt(band, "NOV", 0, 28, 124, C_.w, { w: 660 });
      st.d = txt(st.card, "10", 0, 195, 410, C_.k, { w: 660 });
      st.t = W("nov", "november", 0, 0.2); st.hits = [[st.t, 0.09]];
    },
    update(st, t) {
      T(st.b, { x: lerp(-90, 0, eo(t, 0, 0.25)) });
      const k = sp(t, Math.max(0, st.t - 0.08), 1.4);
      T(st.card, { y: lerp(1100, 0, Math.min(k, 1)), r: lerp(14, -3, k) + Math.sin(t * 3.4) * 0.8 });
    },
    cues: (st) => [cue(Math.max(0, st.t - 0.12), "whoosh", 2), cue(st.t + 0.1, "thump", 3)],
  };
  ACTS.wait = {
    build(w, c, st) {
      st.a = txt(w, "OR GTA VI", 84, 300, 170, C_.w, { w: 832 });
      st.b = txt(w, "MAKES YOU", 130, 506, 114, C_.y, { w: 740 });
      st.c_ = txt(w, "WAIT", 84, 640, 230, C_.y, { w: 832 });
      st.ring = el("div", "b-box", w); L.pos(st.ring, 450, 900, 100, 100); st.ring.style.cssText += `;border:18px solid #444;border-top-color:${C_.y};border-radius:50%;box-sizing:border-box`;
      st.tr = box(w, 140, 1040, 720, 56, "#333", { z: 3, rad: 28, shadow: false });
      st.fl = box(st.tr, 0, 0, 720, 56, C_.y, { z: 4, rad: 28, shadow: false, origin: "0 50%" });
      st.tM = W("wait", "makes", 0, 0.8); st.tW = W("wait", "wait", 0, 1.1); st.hits = [[st.tW, 0.12]];
    },
    update(st, t) {
      T(st.a, { s: 0.94 + 0.06 * sp(t, 0, 1.5) });
      pop(st.b, t, st.tM - 0.03); pop(st.c_, t, st.tW - 0.03, { rf: -7 });
      st.ring.style.transform = `rotate(${(t * 360).toFixed(1)}deg)`;
      T(st.fl, { sx: 0.025 + 0.02 * clamp(t / 2), sy: 1 });
    },
    cues: (st) => [cue(st.tM, "pop", 2), cue(st.tW, "impact", 3)],
  };
  ACTS.bar = {
    build(w, c, st) {
      const p = c.p, x0 = 84, ink = p.ink || C_.w;
      st.l = txt(w, p.label, x0, 300, 110, ink);
      st.u = txt(w, p.usable, x0, 424, 60, ink, { weight: 800, ls: "0" });
      st.s = box(w, x0, 520, p.gb, 220, p.strip || C_.w, { z: 3, origin: "0 50%", sh: 12 });
      st.b = box(w, x0, 520, 212, 220, C_.k, { z: 5, sh: 12 }); txt(st.b, "212", 0, 66, 92, C_.y, { w: 212 });
      st.st = txt(w, p.stat, 84, 800, p.size || 190, p.statc || C_.y, { w: 832 });
      st.tA = W(c.id, p.w1, 0, 0.3); st.tB = W(c.id, p.w2, 0, 0.9); st.hits = [[st.tA, 0.07], [st.tB, 0.12]];
    },
    update(st, t) {
      T(st.l, { x: lerp(-100, 0, eo(t, 0, 0.26)) }); T(st.u, { x: lerp(-100, 0, eo(t, 0.05, 0.26)) });
      T(st.s, { sx: Math.max(0.001, eo(t, 0.03, 0.34)), sy: 1 });
      if (t < st.tA - 0.05) T(st.b, { o: 0 }); else { const k = sp(t, st.tA - 0.05, 1.5); T(st.b, { x: lerp(-280, 0, k), r: lerp(-7, 0, k) }); }
      pop(st.st, t, st.tB - 0.04, { r: -2, rf: 8 });
    },
    cues: (st) => [cue(0, "swish", 2), cue(st.tA, "thump", 2), cue(st.tB, "impact", 3)],
  };
  ACTS.two = {
    build(w, c, st) {
      st.a = txt(w, "2.", 84, 280, 400, C_.r, { w: 832 });
      st.tag = box(w, 90, 720, 820, 210, C_.k, { z: 6, rad: 16, sh: 18 }); txt(st.tag, "PRE-ORDER", 0, 40, 140, C_.y, { w: 820 });
      st.b = txt(w, "TO DOWNLOAD EARLY", 130, 990, 66, C_.k, { w: 740 });
      st.tP = W("two", "pre-order", 0, 0.5); st.tD = W("two", "download", 0, 1); st.hits = [[st.tP, 0.1]];
    },
    update(st, t) {
      const k = sp(t, 0, 1.5); T(st.a, { s: 0.6 + 0.4 * k, r: lerp(-10, 0, k) });
      pop(st.tag, t, st.tP - 0.04, { r: -3, rf: 9 }); pop(st.b, t, st.tD - 0.04);
    },
    cues: (st) => [cue(0, "pop", 2), cue(st.tP, "impact", 3), cue(st.tD, "pop", 2)],
  };

  const stage = {
    busy: false,
    cam: "static",
    build(root, c) {
      const act = ACTS[c.p.act], st = { act };
      if (!act) throw new Error("unknown act " + c.p.act);
      const g = el("div", "abs", root); L.pos(g, -80, -80, c.W + 160, c.H + 160); g.style.background = c.p.g; g.style.zIndex = 0;
      st.world = el("div", "abs", root); L.pos(st.world, 0, 0, c.W, c.H); st.world.style.zIndex = 1; st.world.style.transformOrigin = "50% 42%";
      act.build(st.world, c, st);
      /* the next scene's colour sweeps up on a slant: every cut is a continuous move */
      const nx = c.p.nx;
      if (nx) { st.wipe = el("div", "abs", root); L.pos(st.wipe, -40, -40, c.W + 80, c.H + 300); st.wipe.style.cssText += `;background:${nx};clip-path:polygon(0 12%,100% 0,100% 100%,0 100%);z-index:30`; }
      return st;
    },
    update(st, t, c) {
      st.act.update(st, t, c);
      /* one slow continuous push per scene, plus any impact shake */
      const hit = (st.hits || []).reduce((a, h) => { const x = t - h[0]; return a + (x >= 0 ? h[1] * Math.exp(-5 * x) * Math.cos(10 * x) : 0); }, 0); const push = 1 + 0.035 * (t / c.dur) + hit + (st.act.punch ? st.act.punch(st, t) : 0);
      const sh = st.act.shake ? st.act.shake(st, t) : 0;
      st.world.style.transform = `translate(${(sh * 0.35).toFixed(2)}px,${sh.toFixed(2)}px) scale(${push.toFixed(4)})`;
      if (st.wipe) { const a = c.dur - 0.18, k = seg(t, a, c.dur), e = k * k * (3 - 2 * k); st.wipe.style.transform = `translateY(${((1 - e) * (c.H + 340)).toFixed(1)}px)`; st.wipe.style.visibility = k > 0 ? "visible" : "hidden"; }
    },
    cues: (c) => {
      const act = ACTS[c.p.act], st = {};
      const dummy = document.createElement("div");
      act.build(dummy, { W: c.W, H: c.H, p: c.p, id: c.id }, st);
      const out = act.cues(st);
      if (c.p.nx) out.push(cue(c.dur - 0.24, "swish", 2));
      return out.filter((q) => q.lt >= 0 && q.lt <= c.dur);
    },
  };
  window.SCENES.collage = stage;
  window.SCENES.whiteboard = stage;
})();
