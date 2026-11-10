/* newsstory: the people / news / fact Short. Every frame carries a real photo or real footage, with layered
   elements on top: punchy lines, quote cards, stamps, chips and REAL meme stickers that react to the beat.
   No text, colours or assets are baked in: colours come from the theme (L.C), the display face from the theme
   (var(--display), or params.font), content from params. Everything is a pure function of the scene time t.

   params:
     tag            a chip top-left ("PART 1"); accent: chip colour (default theme accent)
     font           display face for lines, stamps and chips (default the theme display face; register a font in
                    brief.brand.font_files first, for example Anton)
     slides [ ... ]   pictures that cross-cut on spoken words (the first is up from frame 0)
       {src, pos ("50% 25%"), origin, z0 (1.03), z1 (1.14), dx, sat, label, word|at}            a full-frame photo
       {clip, frames, fps, pos, ... }                                                           real footage (ping-pong loop;
                    frames and fps come from build/clips/<clip>/meta.json, cut with `assets clip` or `memes cut`)
       {mode: split, src, src2, pos, pos2, mystery, label}                                     two stacked photos; mystery blurs
                    both (the "which one?" reveal)
       {mode: collage, src, items: [{src, cap, x, y, w, ar, rot, pos, word|at}]}               polaroids on a blurred ground
       label: who or what the picture is and when ("ZENDAYA, TIFF 2024"; "VIDEO: WEF DELHI 2017 · NOT ABOUT THIS").
              Required for photos of people and for footage that is not of the event described.
     lines [{text, word|at, col, size, h, hit}]   stacked headline lines; each pops in on its word (hit: an impact cue)
     ly             top of the line stack as a share of the frame height (default .545)
     fx [ ... ]     layered elements, each lands on `word` (a spoken word) or `at` (seconds):
       {kind: meme, src, top, bottom, x, y, w, rot, until, credit}   a REAL meme picture as a sticker (white border,
                    pop-in, gentle wobble), optional top/bottom captions. src lives under the project (assets/meme/...)
                    and must be registered (`memes add`, `memes templates`, `memes films` + `assets get`): `memes lint`
                    fails a sticker with no credit record. Pick the reaction that matches the beat (shock, side-eye,
                    "wait what", applause); never the same gag twice in one video.
       {kind: emoji, e, x, y, size, rot}         fallback only, when memes.policy is none or nothing fits the beat
       {kind: card, head, body, x, y, w, fs, col, rot}   a white quote card; *word* highlights; quote sources verbatim
       {kind: stamp, text, x, y, w, h, fs, col, rot}     a rotated outline stamp ("UNCONFIRMED", "FEUD?")
       {kind: chip, text, x, y, fs, col, ink}            a pill ("APRIL 2026 · LOS ANGELES", "WATCH PART 2 ▶")
       {kind: flash}                                      a 4-frame white flash
     Keep fx above y 0.66 of the frame: burned-in captions sit below it.
   Cues: swish on a slide change, impact on a hit line or stamp, pop on a meme or emoji, paper on a card. */
(function () {
  "use strict";
  const S = (window.SCENES = window.SCENES || {});
  const { el, seg, eo, clamp, C } = L;
  const when = (c, it, k) => { const w = it.word ? L.wordTime(c, it.word) : null; if (w != null) return Math.max(0, w - 0.08); return it.at != null ? it.at : 0.08 + k * 0.5; };
  const acc = (p) => p.accent || C.accent || "#ffd60a";
  const disp = (p) => (p.font ? `"${p.font}",` : "") + "var(--display),Impact,sans-serif";
  const mark = (x, col) => L.esc(String(x)).replace(/\*([^*]+)\*/g, `<span style="background:${col};color:#111;padding:0 .14em;border-radius:.1em">$1</span>`);
  const url = (p) => (L.projUrl ? L.projUrl(p) : "/project/" + String(p || "").replace(/^\/+/, ""));
  const clipUrl = (clip, n) => `/project/build/clips/${clip}/f_${String(n).padStart(5, "0")}.jpg`;

  function pic(parent, s, W, H) {
    const box = el("div", "abs", parent); L.pos(box, 0, 0, W, H); box.style.overflow = "hidden";
    const im = el("img", "", box);
    const flt = s.mystery ? "blur(30px) brightness(.55) saturate(1.2)" : `saturate(${s.sat || 1.08}) contrast(1.04)`;
    im.style.cssText = `position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;object-position:${s.pos || "50% 25%"};transform-origin:${s.origin || s.pos || "50% 30%"};filter:${flt}`;
    if (s.src) L.setImg(im, url(s.src));
    return { box, im, clip: s.clip, frames: s.frames || 1, fps: s.fps || 30 };
  }

  S.newsstory = {
    busy: true,
    build(root, c) {
      const u = c.u, p = c.p, A = acc(p), F = disp(p), st = { slides: [], lines: [], fx: [] };
      const base = el("div", "abs", root); L.pos(base, 0, 0, c.W, c.H); base.style.background = "#08070c";
      (p.slides || []).forEach((s) => {
        const w = el("div", "abs", root); L.pos(w, 0, 0, c.W, c.H); w.style.overflow = "hidden";
        const o = { w, s, pics: [], items: [] };
        if (s.mode === "split") {
          const a = el("div", "abs", w); L.pos(a, 0, 0, c.W, c.H * 0.5);
          const b = el("div", "abs", w); L.pos(b, 0, c.H * 0.5, c.W, c.H * 0.5);
          o.pics.push(pic(a, { src: s.src, pos: s.pos, mystery: s.mystery }, c.W, c.H * 0.5), pic(b, { src: s.src2, pos: s.pos2, mystery: s.mystery }, c.W, c.H * 0.5));
        } else if (s.mode === "collage") {
          o.pics.push(pic(w, { src: s.src, pos: s.pos, mystery: true }, c.W, c.H));
          (s.items || []).forEach((it, i) => {
            const d = el("div", "abs", w); const bw = (it.w || 0.46) * c.W, bh = bw * (it.ar || 1.25);
            L.pos(d, (it.x || 0.5) * c.W - bw / 2, (it.y || 0.3) * c.H - bh / 2, bw, bh + 70 * u);
            d.style.cssText += `;background:#fff;padding:${14 * u}px ${14 * u}px 0;box-sizing:border-box;box-shadow:0 ${18 * u}px ${50 * u}px rgba(0,0,0,.65)`;
            const f = el("div", "", d); f.style.cssText = `position:relative;width:100%;height:${bh - 14 * u}px;overflow:hidden;background:#222`;
            const im = el("img", "", f); im.style.cssText = `width:100%;height:100%;object-fit:cover;object-position:${it.pos || "50% 20%"}`; L.setImg(im, url(it.src));
            if (it.cap) { const t = el("div", "", d, L.esc(it.cap)); t.style.cssText = `text-align:center;color:#111;font:400 ${40 * u}px/${56 * u}px ${F};letter-spacing:${u}px`; }
            o.items.push({ d, rot: it.rot || 0, t: when(c, it, i), x: i % 2 ? 1 : -1 });
          });
        } else o.pics.push(pic(w, s, c.W, c.H));
        if (s.label) {
          const lb = el("div", "abs", w, L.esc(s.label)); L.pos(lb, c.safe.x, c.safe.y + 92 * u);
          lb.style.cssText += `;max-width:${c.safe.w}px;padding:${7 * u}px ${13 * u}px;border-radius:${6 * u}px;background:rgba(5,5,9,.78);color:#f0f0f2;font:700 ${25 * u}px/1.15 var(--sans),sans-serif;letter-spacing:${0.4 * u}px`;
        }
        st.slides.push(o);
      });
      const scr = el("div", "abs", root); L.pos(scr, 0, 0, c.W, c.H);
      scr.style.cssText += ";background:linear-gradient(180deg,rgba(5,4,10,.45) 0%,rgba(5,4,10,0) 13%,rgba(5,4,10,0) 40%,rgba(5,4,10,.42) 58%,rgba(5,4,10,.5) 100%)";
      if (p.tag) {
        const k = el("div", "abs", root, L.esc(p.tag)); L.pos(k, c.safe.x, c.safe.y + 6 * u);
        k.style.cssText += `;padding:${10 * u}px ${20 * u}px;border-radius:${12 * u}px;background:${A};color:#0a0a0e;font:400 ${40 * u}px/1 ${F};letter-spacing:${u}px`;
      }
      (p.fx || []).forEach((f, i) => {
        const t0 = when(c, f, i), o = { f, t0 };
        const x = (f.x != null ? f.x : 0.5) * c.W, y = (f.y != null ? f.y : 0.5) * c.H;
        if (f.kind === "meme") {
          const w = (f.w || 0.34) * c.W, d = el("div", "abs", root); L.pos(d, x - w / 2, y - w * 0.5, w);
          d.style.cssText += `;background:#fff;padding:${8 * u}px;border-radius:${14 * u}px;box-shadow:0 ${14 * u}px ${36 * u}px rgba(0,0,0,.6);box-sizing:border-box`;
          const fr = el("div", "", d); fr.style.cssText = "position:relative;width:100%;overflow:hidden;border-radius:" + 8 * u + "px";
          const im = el("img", "", fr); im.style.cssText = "display:block;width:100%;height:auto"; L.setImg(im, url(f.src));
          const cap = (t, top) => { if (!t) return; const q = el("div", "", fr, L.esc(t)); q.style.cssText = `position:absolute;left:4%;right:4%;${top ? "top" : "bottom"}:4%;text-align:center;color:#fff;font:400 ${30 * u}px/1.05 ${F};-webkit-text-stroke:${5 * u}px #000;paint-order:stroke fill;text-transform:uppercase`; };
          cap(f.top, true); cap(f.bottom, false);
          o.d = d;
        } else if (f.kind === "emoji") {
          const sz = (f.size || 150) * u, d = el("div", "abs", root, L.esc(f.e)); L.pos(d, x - sz, y - sz * 0.7, sz * 2, sz * 1.4);
          d.style.cssText += `;display:flex;align-items:center;justify-content:center;font:${sz}px/1 "Noto Color Emoji",sans-serif;filter:drop-shadow(0 0 ${3 * u}px #fff) drop-shadow(0 0 ${3 * u}px #fff) drop-shadow(0 ${10 * u}px ${14 * u}px rgba(0,0,0,.6))`;
          o.d = d;
        } else if (f.kind === "card") {
          const w = (f.w || 0.84) * c.W, d = el("div", "abs", root); L.pos(d, x - w / 2, y, w);
          d.style.cssText += `;background:#fff;color:#111;border-radius:${18 * u}px;padding:${22 * u}px ${28 * u}px;box-shadow:0 ${20 * u}px ${60 * u}px rgba(0,0,0,.7);border-left:${12 * u}px solid ${f.col || A};box-sizing:border-box`;
          if (f.head) { const h = el("div", "", d, L.esc(f.head)); h.style.cssText = `font:800 ${25 * u}px/1.2 var(--sans),sans-serif;letter-spacing:${u}px;color:#55555e;margin-bottom:${8 * u}px`; }
          const b = el("div", "", d, mark(f.body || "", f.col || A)); b.style.cssText = `font:800 ${(f.fs || 44) * u}px/1.22 var(--sans),sans-serif`;
          o.d = d;
        } else if (f.kind === "stamp") {
          const w = (f.w || 0.7) * c.W, h = (f.h || 170) * u, d = el("div", "abs", root, L.esc(f.text)); L.pos(d, x - w / 2, y - h / 2, w, h);
          d.style.cssText += `;display:flex;align-items:center;justify-content:center;white-space:nowrap;color:${f.col || "#ff2d3c"};font:400 ${(f.fs || 120) * u}px/1 ${F};border:${11 * u}px solid currentColor;border-radius:${18 * u}px;background:rgba(5,4,10,.5);letter-spacing:${3 * u}px`;
          o.d = d;
        } else if (f.kind === "chip") {
          const d = el("div", "abs", root, L.esc(f.text)); L.pos(d, x, y);
          d.style.cssText += `;white-space:nowrap;transform-origin:0 50%;padding:${12 * u}px ${24 * u}px;border-radius:${50 * u}px;background:${f.col || "#ff2d3c"};color:${f.ink || "#fff"};font:400 ${(f.fs || 50) * u}px/1 ${F};letter-spacing:${u}px;box-shadow:0 ${10 * u}px ${30 * u}px rgba(0,0,0,.55)`;
          o.d = d;
        } else if (f.kind === "flash") { const d = el("div", "abs", root); L.pos(d, 0, 0, c.W, c.H); d.style.background = "#fff"; o.d = d; }
        if (o.d) { o.d.style.opacity = 0; st.fx.push(o); }
      });
      let y = (p.ly != null ? p.ly : 0.545) * c.H;
      (p.lines || []).forEach((it, k) => {
        const h = (it.h || 118) * u, d = el("div", "abs", root, `<div style="width:100%;text-align:center">${L.esc(it.text)}</div>`);
        L.pos(d, c.safe.x - 10 * u, y, c.safe.w + 20 * u, h); y += h + 6 * u;
        d.style.cssText += `;display:flex;align-items:center;justify-content:center;color:${it.col || "#ffffff"};font:400 ${(it.size || 110) * u}px/1 ${F};letter-spacing:${u}px;-webkit-text-stroke:${7 * u}px #08080c;paint-order:stroke fill;text-shadow:0 ${7 * u}px ${18 * u}px rgba(0,0,0,.85)`;
        L.fit(d, (it.size || 110) * u, 36 * u, c.safe.w + 20 * u, h);
        d.style.opacity = 0; st.lines.push({ d, t0: when(c, it, k) });
      });
      st.t = (p.slides || []).map((s, i) => (i === 0 ? 0 : when(c, s, i)));
      return st;
    },
    update(st, t, c) {
      st.slides.forEach((o, i) => {
        const t0 = st.t[i], t1 = i + 1 < st.slides.length ? st.t[i + 1] : c.dur + 1, on = t >= t0 - 1e-4 && t < t1 + 0.06;
        o.w.style.display = on ? "block" : "none"; if (!on) return;
        const s = o.s, k = clamp((t - t0) / Math.max(1, t1 - t0), 0, 1);
        const z0 = s.z0 != null ? s.z0 : 1.03, z1 = s.z1 != null ? s.z1 : 1.14, z = z0 + (z1 - z0) * k, dx = (s.dx || 0) * (k - 0.5) * 70;
        o.pics.forEach((q, j) => {
          q.im.style.transform = `scale(${s.mode === "collage" ? 1.25 : z}) translate(${dx * (j ? -1 : 1)}px,0)`;
          if (q.clip) {                                   /* ping-pong so a short clip never jumps back to frame 1 */
            const n = Math.max(1, q.frames), f = Math.floor((t - t0) * q.fps + 1e-6), m = f % (2 * n - 2 || 1), r = m < n ? m : 2 * n - 2 - m;
            L.setImg(q.im, clipUrl(q.clip, 1 + r));
          }
        });
        o.items.forEach((a) => { const q = eo(seg(t, t0 + a.t, t0 + a.t + 0.25)); a.d.style.opacity = q; a.d.style.transform = `translate(${(1 - q) * a.x * 120}px,${(1 - q) * 40}px) rotate(${a.rot + (1 - q) * a.x * 10}deg) scale(${1 + 0.012 * Math.sin(t * 1.6 + a.x)})`; });
      });
      st.lines.forEach((o) => { const q = seg(t, o.t0, o.t0 + 0.18), e = eo(q); o.d.style.opacity = q > 0 ? 1 : 0; o.d.style.transform = `scale(${1.32 - 0.32 * e})`; });
      st.fx.forEach((o) => {
        const f = o.f;
        if (f.until != null && t > f.until) { o.d.style.opacity = 0; return; }
        if (f.kind === "flash") { o.d.style.opacity = t < o.t0 ? 0 : Math.max(0, 0.85 - (t - o.t0) / 0.14); return; }
        const q = seg(t, o.t0, o.t0 + 0.22), e = eo(q), r = f.rot || 0;
        o.d.style.opacity = q > 0 ? 1 : 0;
        if (f.kind === "emoji" || f.kind === "meme") o.d.style.transform = `scale(${(0.3 + 0.7 * e + 0.3 * Math.sin(q * Math.PI)) * (1 + 0.025 * Math.sin(t * 4 + o.t0))}) rotate(${r + 4 * Math.sin(t * 2.6 + o.t0)}deg)`;
        else if (f.kind === "card") o.d.style.transform = `translateY(${(1 - e) * 70}px) rotate(${r}deg)`;
        else if (f.kind === "stamp") o.d.style.transform = `scale(${1.7 - 0.7 * e}) rotate(${r || -6}deg)`;
        else o.d.style.transform = `scale(${0.6 + 0.4 * e}) rotate(${r}deg)`;
      });
    },
    cues: (c) => {
      const p = c.p, out = [];
      (p.slides || []).forEach((s, i) => { if (i) out.push({ lt: when(c, s, i), type: "swish" }); });
      (p.lines || []).forEach((it, k) => out.push({ lt: when(c, it, k), type: it.hit ? "impact" : "tick" }));
      (p.fx || []).forEach((f, i) => {
        const t = when(c, f, i);
        const type = { meme: "pop", emoji: "pop", stamp: "impact", card: "paper", flash: "flash" }[f.kind];
        if (type) out.push({ lt: t, type });
      });
      return out;
    },
  };
})();
