/* The stage runtime. Loads the resolved timeline for one platform
   (/project/build/timeline-<platform>.json), builds the active scene for
   time t, draws HUD, transitions, burned-in captions and grain, and exposes
   window.STAGE = {init, renderAt, cues, lint, info} to the renderer.

   Scene contract (scenes/*.js register into window.SCENES[type]):
     build(root, c)      -> state   create DOM once per activation
     update(st, t, c)               pure function of local time t (s, design time)
     cues(c)             -> [{lt, type, len?}]   sound-design cues, local time
   c = {W, H, u, mode, P, safe:{x,y,w,h}, dur, beat, bar, p (params), brand, theme, id, index} */
(function () {
  "use strict";
  const { el, pos, seg, eo, ei, eio, clamp } = L;
  const qs = new URLSearchParams(location.search);
  const PLATFORM = qs.get("p") || "youtube";
  let TL = null, W = 0, H = 0, DUR = 0, items = [], CAPS = [], POP = [], CAPSTYLE = "karaoke", LINTING = false, stage, layers = {};

  const modeOf = (w, h) => { const r = w / h; return r >= 1.45 ? "land" : r >= 0.95 ? "square" : r >= 0.7 ? "port" : "tall"; };

  async function loadScript(src) {
    await new Promise((res, rej) => { const s = document.createElement("script"); s.src = src; s.onload = res; s.onerror = () => rej(new Error("failed to load " + src)); document.head.appendChild(s); });
  }

  async function init() {
    const r = await fetch(`/project/build/timeline-${PLATFORM}.json`, { cache: "no-store" });
    if (!r.ok) throw new Error(`timeline-${PLATFORM}.json missing: run \`fishvideo storyboard\``);
    TL = await r.json();
    /* "none", "n/a" or empty is not a brand name */
    if (TL.brand && /^(\s*|none|n\/a|na|null|-+)$/i.test(String(TL.brand.name == null ? "" : TL.brand.name))) { TL.brand.name = ""; TL.brand.explicit_name = false; }
    W = TL.W; H = TL.H; DUR = TL.duration;
    L.FPS = TL.fps || 30;
    L.setTempo(TL.bpm || 120, TL.beats_per_bar || 4);
    L.applyTheme(TL.theme || {});
    for (const f of (TL.theme && TL.theme.font_files) || []) {
      const ff = new FontFace(f.family, `url(/project/${f.src.replace(/^\/+/, "")})`, { weight: String(f.weight || 400), style: f.style || "normal" });
      document.fonts.add(await ff.load());
    }
    for (const s of TL.custom_scenes || []) await loadScript("/project/" + s.replace(/^\/+/, ""));
    const fams = ['400 20px "Inter"', '600 20px "Inter"', '700 20px "Inter"', '800 20px "Inter"', '900 20px "Inter"', '400 20px "JetBrains Mono"', '600 20px "JetBrains Mono"', '700 20px "JetBrains Mono"', '500 20px "Fraunces"', 'italic 400 20px "Fraunces"', '700 20px "Caveat"', '600 20px "Caveat"'];
    if (TL.lang && /^(hi|mr|ne|sa)/.test(TL.lang)) fams.push('400 20px "Noto Sans Devanagari"', '700 20px "Noto Sans Devanagari"');
    /* theme fonts (config/themes.yaml): load the weights a scene may use before the first frame */
    for (const f of Object.values((TL.theme && TL.theme.fonts) || {})) for (const w of [400, 500, 700, 900]) fams.push(`${w} 20px "${f}"`);
    await Promise.all(fams.map((f) => document.fonts.load(f).catch(() => {})));
    await document.fonts.ready;
    if ((TL.shots || []).length) await L.loadMeta(TL.shots);
    L.grainTiles();
    L.defs();
    /* cut-outs are laid out by their opaque bbox: measure them all before any scene builds */
    await Promise.all(TL.scenes.flatMap((s) => L.cutSources(s.params || {})).map((u) => L.measureCut(u)));

    stage = document.getElementById("stage");
    stage.style.width = W + "px"; stage.style.height = H + "px";
    const C = L.C;
    const bg = el("div", "", stage); bg.id = "bg";
    /* texture: paper | grain | clean | grid | blueprint (null = the classic wash + dots) */
    const TEX = TL.texture || null;
    const wash = `<div class="wash" style="background:radial-gradient(ellipse at 30% 20%, ${L.hexA(C.surface, 1)} 0%, transparent 60%), radial-gradient(ellipse at 80% 90%, ${L.hexA(C.ink, 0.06)} 0%, transparent 55%), ${C.bg}"></div>`;
    if (TEX === "paper") {
      /* crumpled paper, generated once per page (SVG lighting -> canvas), never fetched */
      const u = await L.texture("paper", W, H);
      bg.innerHTML = `<img class="tex" alt="" src="${u}" style="position:absolute;left:0;top:0;width:${W}px;height:${H}px">`;
      await bg.firstChild.decode().catch(() => {});
    } else if (L.TEXTURES_CSS.includes(TEX) && TEX !== "grid" && TEX !== "blueprint") bg.innerHTML = `<div class="abs" style="inset:0;${L.textureCSS(TEX, C)}"></div>`;
    else if (TEX === "grid" || TEX === "blueprint") bg.innerHTML = `<div class="abs" style="inset:0;${L.textureCSS(TEX, C)}"></div>${TEX === "blueprint" ? '<div class="abs" style="inset:0;background:radial-gradient(ellipse at 50% 45%, transparent 50%, rgba(0,0,0,.35) 100%)"></div>' : ""}`;
    else if (TEX === "clean" || TEX === "grain") bg.innerHTML = wash;
    else bg.innerHTML = TL.background === "plain" ? "" : `${wash}${TL.background === "dots" || !TL.background ? '<div class="dots"></div>' : ""}`;
    layers.scenes = el("div", "", stage); layers.scenes.id = "scenes";
    layers.hud = el("div", "", stage); layers.hud.id = "hud";
    layers.caps = el("div", "", stage); layers.caps.id = "caps";
    layers.fx = el("div", "", stage); layers.fx.id = "fx";
    if (TL.vignette !== false) { layers.vign = el("div", "", stage); layers.vign.id = "vign"; }
    layers.grain = el("div", "", stage); layers.grain.id = "grain";
    if (TL.grain === false || TEX === "clean") layers.grain.style.display = "none";
    if (TEX === "grain" || TEX === "paper") layers.grain.style.opacity = TEX === "grain" ? 0.11 : 0.07;

    const S = TL.safe || { top: 60, right: 60, bottom: 60, left: 60 };
    /* captions.style: pop | karaoke (default) | minimal | none (an object is the legacy {size}) */
    const rawStyle = TL.captions && TL.captions.style;
    CAPSTYLE = typeof rawStyle === "string" ? rawStyle : "karaoke";
    const burn = TL.captions && TL.captions.burn && CAPSTYLE !== "none";
    const capH = burn ? TL.captions.reserve || Math.round(H * (CAPSTYLE === "pop" ? 0.1 : CAPSTYLE === "minimal" ? 0.12 : 0.17)) : 0;
    const base = { W, H, minPx: (TL.legibility && TL.legibility.min_px) || 22, u: Math.min(W, H) / 1080, mode: modeOf(W, H), brand: TL.brand || {}, theme: TL.theme || {}, beat: L.BEAT, bar: L.BAR, fps: L.FPS, lang: TL.lang || "en", sfx: (typeof TL.sfx === "string" ? TL.sfx : TL.sfx && TL.sfx.density) || "standard", texture: TEX };
    base.P = base.mode === "port" || base.mode === "tall";
    base.safe = { x: S.left, y: S.top, w: W - S.left - S.right, h: H - S.top - S.bottom - capH };
    base.capTop = H - S.bottom - capH;
    base.styled = !!TL.style;
    items = TL.scenes.map((s, i) => {
      const ts = s.ts || 1;
      /* the words spoken in this scene, in scene time: scenes can land things on them */
      const words = (TL.words || []).filter((w) => w.t0 >= s.t0 && w.t0 < s.t1).map((w) => ({ w: w.w, lt: (w.t0 - s.t0) * ts, lt1: (w.t1 - s.t0) * ts }));
      return { ...s, i, c: { ...base, id: s.id, index: i, dur: (s.t1 - s.t0) * ts, ts, p: s.params || {}, words } };
    });
    for (const it of items) if (!window.SCENES[it.type]) throw new Error(`unknown scene type "${it.type}" (scene ${it.id})`);
    /* busy scenes get a 40% backing plate under pop captions (params.plate overrides) */
    for (const it of items) { const pl = it.c.p.plate != null ? it.c.p.plate : it.plate; it.busy = pl != null ? !!pl : !!window.SCENES[it.type].busy; }
    /* the camera rig: scene-level fields win over params; the scene type gives the default style */
    for (const it of items) {
      const c = it.c, p = c.p, pick = (k) => (it[k] != null ? it[k] : p[k]);
      c.cam = { camera: pick("camera"), camera_from: pick("camera_from"), camera_shake: pick("camera_shake"), camera_shake_on: pick("camera_shake_on"), camera_blend: pick("camera_blend"), dof: pick("dof"), dof_max: pick("dof_max"), dof_text: pick("dof_text") };
      c.def = window.SCENES[it.type];
      /* legacy briefs (no style, no camera) stay static */
      /* the older scenes run type edge to edge: their default push stays small */
      c.defCam = c.def.cam || (c.styled && L.rig.STYLED[it.type] ? { preset: L.rig.STYLED[it.type], amount: 0.5 } : "static");
      c.lively = (c.styled || c.cam.camera != null) && c.defCam !== "screen" && it.type !== "tour" && it.type !== "thumbnail";
      c.prev = it.i > 0 ? items[it.i - 1].c : null;
      c.first = items[0].c;
      /* the scene stays up through its cut unless it fades */
      {
        const nx = TL.scenes[it.i + 1];
        const kind = nx ? nx.transition || "fade" : null;
        c.holdOut = !!nx && kind !== "fade" && (c.styled || kind === "defocus" || kind === "match");
        /* a colour only: thumbnail and kinetic use params.accent for a word or a switch */
        const ac = pick("accent");
        c.accent = typeof ac === "string" && /^#[0-9a-f]{3,8}$/i.test(ac.trim()) ? ac.trim() : null;
        /* entrances run ahead of the clock and converge by 1.2 s: every scene opens with its subject up */
        const lead = pick("lead");
        const noLead = it.type === "tour" || it.type === "footage" || it.type === "thumbnail" || it.type === "stepcard";
        c.lead = lead != null ? +lead : c.styled && !noLead ? (it.i === 0 ? 0.6 : 0.45) : 0;
        c.carry = pick("carry");
      }
    }

    // HUD
    layers.chap = el("div", "chapter", layers.hud);
    layers.chap.style.right = S.right + "px"; layers.chap.style.top = Math.max(24, S.top * 0.6) + "px";
    layers.rail = el("div", "rail", layers.hud, "<i></i>");
    pos(layers.rail, 0, H - 4, W, 4);
    if (!TL.hud || TL.hud.rail === false) layers.rail.style.display = "none";
    // captions
    layers.capBox = el("div", "capbox", layers.caps);
    layers.capBox.style.left = S.left + "px"; layers.capBox.style.right = S.right + "px";
    layers.capBox.style.top = base.capTop + 12 + "px";
    layers.capInner = el("div", "", layers.capBox);
    const cs = typeof rawStyle === "object" && rawStyle ? rawStyle : {};
    layers.capFont = cs.size || (TL.captions && TL.captions.size) || Math.round((CAPSTYLE === "pop" ? 78 : CAPSTYLE === "minimal" ? 40 : 44) * base.u);
    CAPS = (TL.captions && TL.captions.cues) || [];
    if (CAPSTYLE === "pop") {
      layers.capBox.classList.add("pop");
      layers.capBox.style.height = capH - 12 + "px";
      POP = L.capGroups(TL.words && TL.words.length ? TL.words : CAPS.flatMap((q) => q.words || []), TL.captions.delivery);
    }
    // transitions
    layers.wipe = el("div", "abs", layers.fx);
    layers.wipe.innerHTML = `<div class="abs" style="inset:0;background:${C.ink}"></div><div class="abs" style="top:0;bottom:0;width:26px;right:-26px;background:${C.accent}"></div>`;
    pos(layers.wipe, 0, 0, W, H);
    layers.fade = el("div", "abs", layers.fx);
    pos(layers.fade, 0, 0, W, H);
    layers.fade.style.background = C.bg;
    layers.flash = el("div", "abs", layers.fx);
    pos(layers.flash, 0, 0, W, H);
    layers.flash.style.background = "#fff";
    layers.flash.style.visibility = "hidden";
    layers.flood = el("div", "abs", layers.fx);
    pos(layers.flood, 0, 0, W, H);
    layers.flood.style.background = C.accent;
    layers.flood.style.visibility = "hidden";
    layers.dip = el("div", "abs", layers.fx);
    pos(layers.dip, 0, 0, W, H);
    layers.dip.style.background = "#000";
    layers.dip.style.visibility = "hidden";
    return info();
  }

  function info() {
    return {
      platform: PLATFORM, W, H, fps: L.FPS, duration: DUR, frames: Math.round(DUR * L.FPS), bpm: L.BPM, bars: TL.bars,
      music: TL.music, chapters: items.filter((q) => q.chapter).map((q) => ({ t: q.t0, title: q.chapter })),
    };
  }

  let cur = null;
  function activate(it) {
    if (cur && cur.it === it) return cur;
    if (cur) cur.root.remove();
    const root = el("div", "layer", layers.scenes);
    root.dataset.scene = it.id;
    root.style.perspective = L.rig.P(it.c) + "px";
    /* the world the camera looks at: scenes build into it, L.layer() adds depth planes */
    const world = el("div", "fv-world", root);
    pos(world, 0, 0, W, H);
    world.dataset.p = L.rig.P(it.c);
    world.style.transformOrigin = "50% 50%";
    const def = window.SCENES[it.type];
    const st = withAccent(it.c, root, () => def.build(world, it.c));
    cur = { it, root, world, st, def };
    buildCarry(cur);
    return cur;
  }

  /* per-beat accent: the scene's CSS variables, and L.C while its code runs */
  function withAccent(c, root, fn) {
    if (!c.accent) return fn();
    if (root && !root._acc) {
      root._acc = true;
      root.style.setProperty("--accent", c.accent);
      root.style.setProperty("--accent-soft", L.hexA(c.accent, 0.14));
    }
    const a = L.C.accent, b = L.C.accentSoft;
    L.C.accent = c.accent; L.C.accentSoft = L.hexA(c.accent, 0.14);
    try { return fn(); } finally { L.C.accent = a; L.C.accentSoft = b; }
  }

  /* Scene clock: ahead by c.lead at the cut, converging on real time by 1.2 s. */
  const WARP = 1.2;
  const warp = (c, lt) => (c.lead ? lt + c.lead * (1 - seg(lt, 0, WARP)) : lt);

  /* The persistent character: storyboard `anchor`, or per-scene `carry` (false = none here).
     Placed once per activation, against the scene's finished layout, so it never covers text. */
  function buildCarry(s) {
    const c = s.it.c, d = c.carry === false ? null : c.carry || TL.anchor;
    s.carry = null;
    if (!d || !d.src || s.it.type === "thumbnail") return;
    const url = L.projUrl(d.src), info = L.cutInfo(url);
    const heroes = (s.st && s.st.heroes) || [];
    if (!c.carry && heroes.some((h) => h.url === url)) return; /* the character is already on stage */
    const u = c.u, sb = stage.getBoundingClientRect(), scale = sb.width / W;
    try { withAccent(c, s.root, () => s.def.update(s.st, Math.max(0, c.dur - 0.32), c)); } catch (e) { return; }
    const rects = [];
    const toR = (r) => ({ x: (r.left - sb.left) / scale, y: (r.top - sb.top) / scale, w: r.width / scale, h: r.height / scale });
    const tw = document.createTreeWalker(s.world, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = tw.nextNode())) {
      if (!n.textContent.trim() || n.parentElement.closest("svg")) continue;
      const q = toR(n.parentElement.getBoundingClientRect());
      if (q.w > 1 && q.h > 1) rects.push(q);
    }
    s.world.querySelectorAll("[data-obst], .node").forEach((e) => rects.push(toR(e.getBoundingClientRect())));
    const occ = [...s.world.querySelectorAll(".fv-card")].map((e) => e._occ).filter(Boolean);
    const asp = info ? (info.h * info.nh) / (info.w * info.nw) : 1;
    const bounds = { x0: 30 * u, y0: 80 * u, x1: W - 30 * u, y1: c.safe.y + c.safe.h - 8 * u };
    const tilt = Math.abs(((d.rot != null ? +d.rot : -6) * Math.PI) / 180) + 0.04, cs = Math.cos(tilt), sn = Math.sin(tilt);
    let w = (d.w || 0.2) * c.safe.w, spot = null;
    for (const f of [1, 0.8, 0.65]) {
      /* placed by its tilted box (+ drift): the type sits on a nearer plane, so keep a wide berth */
      const w0 = w * f, h0 = w0 * asp, ww = w0 * cs + h0 * sn, hh = w0 * sn + h0 * cs, cor = d.corner || "br";
      const want = d.x != null || d.y != null
        ? { x: c.safe.x + (d.x != null ? d.x : 0.85) * c.safe.w - ww / 2, y: c.safe.y + (d.y != null ? d.y : 0.85) * c.safe.h - hh / 2 }
        : { x: cor[1] === "l" ? c.safe.x : c.safe.x + c.safe.w - ww, y: cor[0] === "t" ? c.safe.y : bounds.y1 - hh };
      spot = L.placeLabel({ w: ww, h: hh, want, bounds, hit: (x, y) => occ.some((o) => o(x, y)), rects, step: 16 * u, pad: 26 * u });
      if (spot.free) { spot = { x: spot.x + (ww - w0) / 2, y: spot.y + (hh - h0) / 2 }; w = w0; break; }
      spot = null;
    }
    if (!spot) return;
    const node = el("div", "fv-cut", s.world);
    node.dataset.nolint = "";
    const h = w * asp;
    pos(node, spot.x, spot.y, w, h);
    const img = el("img", "", node);
    if (info) { const iw = w / info.w, ih = h / info.h; img.style.cssText = `position:absolute;left:${(-info.x * iw).toFixed(2)}px;top:${(-info.y * ih).toFixed(2)}px;width:${iw.toFixed(2)}px;height:${ih.toFixed(2)}px;max-width:none`; }
    L.setImgFx(img, url, d.halftone === false ? null : { bw: true, halftone: true, contrast: d.contrast || 1.3 });
    node.style.filter = L.cutFilter({ outline: 4 * u, shadow: { x: 8 * u, y: 12 * u, blur: 14 * u, a: 0.5 } });
    node.style.transformOrigin = "50% 60%";
    L.layer(node, 60, { sharp: true });
    s.carry = { node, at: d.at != null ? +d.at : 0, rot: d.rot != null ? +d.rot : -6, kicks: L.rig.kicks(c) };
  }
  function carryAt(s, lt) {
    const q = s.carry;
    if (!q) return;
    const d = lt - q.at;
    if (d < 0) { q.node.style.visibility = "hidden"; return; }
    let kick = 0;
    for (const k of q.kicks) kick += L.punch(lt - k, 16, 5);
    const a = L.spring(d + (q.at ? 0 : 1), L.SPRING.playful), TAU = Math.PI * 2;
    q.node.style.visibility = "visible";
    q.node.style.transform = `translateY(${(6 * s.it.c.u * Math.sin((TAU * lt) / 3.7) - 26 * s.it.c.u * kick).toFixed(2)}px) rotate(${(q.rot + 2.2 * Math.sin((TAU * lt) / 5.3) + 7 * kick).toFixed(3)}deg) scale(${(a * (1 + 0.1 * kick)).toFixed(4)})`;
  }

  /* ---------------- overlap: the outgoing scene stays alive over the incoming one ---------------- */
  let ghost = null, flyer = null;
  const dropGhost = () => { if (ghost) { ghost.root.remove(); ghost = null; } if (flyer) { flyer.node.remove(); flyer = null; } };
  function ghostOf(pit) {
    if (ghost && ghost.it === pit) return ghost;
    dropGhost();
    const root = el("div", "layer", layers.scenes);
    root.style.zIndex = 3;
    root.dataset.nolint = "";
    root.style.perspective = L.rig.P(pit.c) + "px";
    const world = el("div", "fv-world", root);
    pos(world, 0, 0, W, H);
    world.dataset.p = L.rig.P(pit.c);
    world.style.transformOrigin = "50% 50%";
    const def = window.SCENES[pit.type];
    const st = withAccent(pit.c, root, () => def.build(world, pit.c));
    return (ghost = { it: pit, root, world, st, def, carry: null });
  }
  function cutClone(h, parent) {
    const box = el("div", "abs", parent);
    pos(box, 0, 0, h.w, h.h);
    box.style.transformOrigin = "0 0";
    const img = el("img", "", box);
    const info = L.cutInfo(h.url);
    if (info && h.kind === "cutout") { const iw = h.w / info.w, ih = h.h / info.h; img.style.cssText = `position:absolute;left:${(-info.x * iw).toFixed(2)}px;top:${(-info.y * ih).toFixed(2)}px;width:${iw.toFixed(2)}px;height:${ih.toFixed(2)}px;max-width:none`; }
    else img.style.cssText = "position:absolute;inset:0;width:100%;height:100%;object-fit:cover";
    L.setImgFx(img, h.url, h.fx);
    if (h.base) box.style.filter = h.base;
    return box;
  }
  function pairHeroes(la, lb) {
    if (!la || !lb || !la.length || !lb.length) return null;
    for (const a of la) for (const b of lb) if (a.url === b.url) return [a, b];
    return [la.find((q) => q.match) || la[0], lb.find((q) => q.match) || lb[0]];
  }
  const DISSOLVE = 0.36;
  function drawOverlap(t, it) {
    if (LINTING || it.i === 0) return dropGhost();
    const kind = it.transition, dIn = t - it.t0, prev = items[it.i - 1], c = it.c;
    const span = kind === "match" ? clamp(+(c.p.match_dur != null ? c.p.match_dur : 0.5), 0.2, 1.2) : DISSOLVE;
    if ((kind !== "defocus" && kind !== "match") || dIn >= span) return dropGhost();
    const g = ghostOf(prev), pc = prev.c, lg = pc.dur - 1e-3 + dIn * pc.ts;
    withAccent(pc, g.root, () => g.def.update(g.st, lg, pc));
    L.rig.apply(g.root, g.world, pc, L.rig.pose(pc, lg), false);
    if (kind === "defocus") {
      /* the sharp incoming subject shows through the blurring outgoing one */
      const q = L.EASE.camera(dIn / DISSOLVE);
      g.root.style.opacity = (1 - q).toFixed(3);
      g.root.style.filter = `blur(${(q * 14).toFixed(2)}px)`;
      g.root.style.transform = `scale(${(1 + 0.03 * q).toFixed(4)})`;
      return;
    }
    /* match: the rest of A dissolves fast while its hero flies to its place in B */
    g.root.style.opacity = (1 - L.EASE.camera(seg(dIn, 0, Math.min(0.22, span)))).toFixed(3);
    const pair = pairHeroes(g.st.heroes, cur.st.heroes);
    if (!pair) return;
    const [a, b] = pair;
    const q = L.EASE.camera(dIn / span);
    const sb = stage.getBoundingClientRect(), k = sb.width / W;
    const box = (h) => { const r = h.node.getBoundingClientRect(), an = Math.abs((h.rot * Math.PI) / 180), ex = h.w * Math.cos(an) + h.h * Math.sin(an); return { cx: (r.left + r.width / 2 - sb.left) / k, cy: (r.top + r.height / 2 - sb.top) / k, s: r.width / k / Math.max(1, ex) }; };
    const A = box(a), Bb = box(b);
    a.node.style.visibility = "hidden";
    b.node.style.visibility = "hidden";
    if (!flyer) {
      const node = el("div", "abs", layers.scenes);
      pos(node, 0, 0, W, H);
      node.style.zIndex = 5; node.style.pointerEvents = "none";
      flyer = { node, a: cutClone(a, node), b: a.url === b.url ? null : cutClone(b, node) };
    }
    const lift = -Math.sin(Math.PI * q) * 46 * c.u, bump = 1 + 0.07 * Math.sin(Math.PI * q);
    const cx = L.lerp(A.cx, Bb.cx, q), cy = L.lerp(A.cy, Bb.cy, q) + lift;
    const wNow = L.lerp(a.w * A.s, b.w * Bb.s, q) * bump, rNow = L.lerp(a.rot, b.rot, q);
    const place = (e, h, o) => { const sc = wNow / h.w; e.style.opacity = o; e.style.transform = `translate(${cx.toFixed(2)}px, ${cy.toFixed(2)}px) rotate(${rNow.toFixed(3)}deg) scale(${sc.toFixed(4)}) translate(${(-h.w / 2).toFixed(2)}px, ${(-h.h / 2).toFixed(2)}px)`; };
    place(flyer.a, a, flyer.b ? (1 - q).toFixed(3) : 1);
    if (flyer.b) place(flyer.b, b, q.toFixed(3));
  }


  function chapterAt(t) { let ch = null, at = 0; for (const it of items) { if (it.t0 > t) break; if (it.chapter) { ch = it.chapter; at = it.t0; } } return { ch, at }; }

  function drawHud(t, it) {
    if (!TL.hud || TL.hud.chapter === false) layers.chap.style.opacity = 0;
    else {
      const { ch, at } = chapterAt(t);
      const hide = !ch || it.hud === false || ["title", "end", "thumbnail", "kinetic"].includes(it.type) && it.hud !== true;
      if (hide) layers.chap.style.opacity = 0;
      else {
        const parts = ch.split(" · ");
        layers.chap.innerHTML = parts.length > 1 ? `<b>${L.esc(parts[0])}</b><i></i>${L.esc(parts[1])}` : `<b>●</b>${L.esc(ch)}`;
        layers.chap.style.opacity = eo(seg(t, at + 0.4, at + 1.0));
      }
    }
    layers.rail.firstChild.style.width = ((t / DUR) * 100).toFixed(3) + "%";
    layers.rail.style.opacity = it.type === "thumbnail" || it.index === 0 ? 0 : 0.9;
  }

  /* burned-in captions: the current cue, words lit as they are spoken */
  function drawCaption(t, it) {
    if (!TL.captions || !TL.captions.burn || CAPSTYLE === "none") return;
    if (CAPSTYLE === "pop") return drawPop(t, it);
    const c = CAPS.find((q) => t >= q.start && t < q.end);
    if (!c) { layers.capInner.innerHTML = ""; return; }
    const words = c.words && c.words.length ? c.words : c.text.split(" ").map((w, i, a) => ({ w, t0: c.start + ((c.end - c.start) * i) / a.length }));
    let k = -1;
    words.forEach((w, i) => { if (t >= w.t0) k = i; });
    const a = eo(seg(t, c.start, c.start + 0.18)) * (1 - ei(seg(t, c.end - 0.12, c.end)));
    layers.capInner.innerHTML = `<span class="cap${CAPSTYLE === "minimal" ? " cap-min" : ""}" style="font-size:${layers.capFont}px">${words.map((w, i) => `<span class="w${i <= k ? " on" : ""}${i === k ? " now" : ""}">${L.esc(w.w)}</span>`).join(" ")}</span>`;
    layers.capInner.style.opacity = a;
    layers.capInner.style.transform = `translateY(${(1 - eo(seg(t, c.start, c.start + 0.25))) * 14}px)`;
  }

  /* pop: huge Inter 900, the spoken word in the accent, a 4-frame scale pop */
  function drawPop(t, it) {
    const g = POP.find((q) => t >= q.start && t < q.end);
    if (!g) { layers.capInner.innerHTML = ""; return; }
    let k = 0;
    g.ws.forEach((w, i) => { if (t >= w.t0) k = i; });
    /* the band is reserved and the type carries its own stroke: a plate only over moving pictures (low local contrast) */
    const plate = it && it.busy;
    layers.capInner.innerHTML = `<span class="cap-pop${plate ? " plate" : ""}">${g.ws.map((w, i) => `<span class="w${i === k ? " now" : ""}">${L.esc(w.w)}</span>`).join(" ")}</span>`;
    const node = layers.capInner.firstChild;
    if (g.px == null) {
      /* base 78 down to 42 (at u = 1), at most 900 wide in portrait: one line if it stays big, else two */
      const bw = Math.min(layers.capBox.clientWidth || W * 0.8, it.c.P ? 900 * it.c.u : Infinity);
      const F = layers.capFont, floor = 42 * it.c.u;
      g.px = L.fit(node, F, Math.max(floor, F * 0.72), bw, F * 1.3);
      if (node.scrollWidth > bw + 1 || node.scrollHeight > F * 1.3 + 1) g.px = L.fit(node, F, floor, bw, F * 2.4);
    }
    node.style.fontSize = g.px + "px";
    const p = eo(seg(t, g.start, g.start + 4 / L.FPS));
    /* exit fade 0.12 s after the last word, then hard off; a group that hands straight to the next one just swaps */
    const out = g.end - g.last >= 0.12 ? ei(seg(t, g.end - 0.12, g.end)) : 0;
    layers.capInner.style.opacity = clamp(p * 2) * (1 - out);
    layers.capInner.style.transform = `scale(${(0.85 + 0.15 * p).toFixed(4)})`;
  }

  /* transitions: fade | wipe | cut | zoom (portal) | flash | defocus | flip | flood | dip | iris | through | world */
  const FLASHY = new Set(["zoom", "flash"]);
  /* the camera: scene move + follow hint + portal z-moves of zoom cuts + lens (motion blur, vignette) */
  function drawCamera(t, it, lt, s) {
    const c = it.c, R = L.rig;
    const o = R.pose(c, lt);
    const sp = R.spec(c);
    const fw = s.st && s.st.camFollow != null ? s.st.camFollow : sp.follow;
    if (fw && s.st && s.st.camHint) { o.x += (s.st.camHint.x - W / 2) * fw; o.y += (s.st.camHint.y - H / 2) * fw; }
    if (s.st && s.st.camZ) o.z += s.st.camZ;
    if (s.st && s.st.camKick) o.z += s.st.camKick;
    /* the hook moves at once: a fast spring push from t = 0 */
    if (it.i === 0 && c.lively && c.p.hook_motion !== false) o.z -= 90 * c.u * (1 - L.spring(lt, HOOK_SPRING));
    const P = R.P(c), next = items[it.i + 1];
    const dIn = t - it.t0, dOut = it.t1 - t;
    if (it.i > 0 && it.transition === "zoom") o.z += (1 - L.portal(seg(dIn, 0, 0.75))) * 0.31 * P;
    if (next && next.transition === "zoom") o.z += ei(1 - seg(dOut, 0, 0.32)) * 0.68 * P;
    o.z = Math.min(o.z, 0.93 * P);
    const zf = R.apply(s.root, s.world, c, o, LINTING);
    if (layers.vign) layers.vign.style.background = `radial-gradient(ellipse at 50% 45%, transparent ${(55 - clamp((zf - 1) * 30, 0, 12)).toFixed(1)}%, rgba(0,0,0,${(0.12 + clamp((zf - 1) * 0.35, 0, 0.22)).toFixed(3)}) 100%)`;
    if (LINTING || !R.active(c)) return "";
    const v = R.speed(c, lt);
    if (v.v <= R.THRESH) return "";
    const amt = Math.min(6, (v.v - R.THRESH) * 0.22); /* full-frame peak 18 px */
    return v.lateral ? L.mbFilter(amt) : `blur(${(amt * 0.8).toFixed(2)}px)`;
  }

  function drawTransitions(t, it, lt, camFilter) {
    /* the 2-frame white flash of zoom / flash cuts, then a quick fade */
    let fl = 0;
    const fr = 1 / L.FPS, eps = 1e-6;
    for (const q of items) {
      if (q.i === 0 || !FLASHY.has(q.transition)) continue;
      const d = t - q.t0;
      if (d >= -fr - eps && d < fr - eps) fl = Math.max(fl, q.transition === "flash" ? 0.96 : 1);
      /* a styled zoom is exactly the 2-frame flash; a flash cut lets go quickly, without a wash */
      else if (q.transition === "flash" && d >= fr - eps && d < fr + (q.c.styled ? 0.08 : 0.18)) fl = Math.max(fl, (1 - eo((d - fr) / (q.c.styled ? 0.08 : 0.18))) * (q.c.styled ? 0.5 : 0.9));
      else if (q.transition === "zoom" && !q.c.styled && d >= fr - eps && d < fr + 0.18) fl = Math.max(fl, (1 - eo((d - fr) / 0.18)) * 0.9);
    }
    layers.flash.style.opacity = fl;
    layers.flash.style.visibility = fl > 0.001 ? "visible" : "hidden";
    let wiped = false;
    for (const q of items) {
      if (q.transition !== "wipe" || q.i === 0) continue;
      const a = q.t0 - 0.34, b = q.t0 + 0.34;
      if (t >= a && t <= b) {
        const p = (t - a) / (b - a);
        const x = p < 0.5 ? -W + eio(p * 2) * W : eio((p - 0.5) * 2) * W;
        layers.wipe.style.transform = `translateX(${x.toFixed(1)}px) skewX(-8deg)`;
        layers.wipe.style.width = W * 1.2 + "px"; layers.wipe.style.left = -W * 0.1 + "px";
        layers.wipe.style.visibility = "visible";
        wiped = true;
      }
    }
    if (!wiped) layers.wipe.style.visibility = "hidden";
    /* colour flood: 0.2 s closing over A, 0.2 s lifting off B (0.4 s, power2.inOut) */
    let flood = null;
    for (const q of items) {
      if (q.i === 0 || q.transition !== "flood") continue;
      const d = t - q.t0;
      if (d >= -0.2 && d < 0) flood = { r: L.EASE.flood((d + 0.2) / 0.2), o: 1 };
      else if (d >= 0 && d < 0.2) flood = { r: 1, o: 1 - L.EASE.flood(d / 0.2) };
    }
    layers.flood.style.visibility = flood ? "visible" : "hidden";
    if (flood) { layers.flood.style.opacity = flood.o; layers.flood.style.clipPath = `circle(${(flood.r * 120).toFixed(2)}% at 50% 46%)`; }
    /* dip cut: darken 40% for 3 frames around the cut */
    let dip = false;
    for (const q of items) { if (q.i && q.transition === "dip") { const d = t - q.t0; if (d >= -fr - eps && d < 2 * fr - eps) dip = true; } }
    layers.dip.style.visibility = dip ? "visible" : "hidden";
    layers.dip.style.opacity = dip ? 0.4 : 0;
    // per-scene soft in/out unless the cut is hard
    const next = items[it.i + 1];
    const outKind = next ? next.transition || "fade" : "fade";
    const inKind = it.transition || "fade";
    const d = it.c.dur, u = 0.22 * it.c.ts;
    let o = 1, blur = 0;
    if (inKind === "fade" && it.i > 0) o = Math.min(o, eo(seg(lt, 0, u)));
    if (outKind === "fade" && next) { const q = ei(seg(lt, d - u, d)); o = Math.min(o, 1 - q); blur = q * 6; }
    let sc = 1, ry = 0;
    const dIn = t - it.t0, dOut = it.t1 - t;
    if (it.i > 0) {
      if (inKind === "zoom") blur += (1 - eo(seg(dIn, 0, it.c.styled ? 0.16 : 0.3))) * (it.c.styled ? 5 : 10); /* the pull-back itself is a camera z-move */
      else if (inKind === "flash") sc *= 1.06 - 0.06 * L.portal(seg(dIn, 0, 0.5));
      /* defocus: B is sharp at once; A blurs away over it (drawOverlap) */
      else if (inKind === "flip") { const q = eo(seg(dIn, 0, 0.34)); ry = -90 * (1 - q); sc *= 0.9 + 0.1 * q; }
    }
    if (next) {
      if (outKind === "zoom") blur += ei(1 - seg(dOut, 0, 0.32)) * (it.c.styled ? 9 : 16);
      else if (outKind === "flip") { const q = ei(1 - seg(dOut, 0, 0.28)); ry = 90 * q; sc *= 1 - 0.1 * q; }
    }
    /* iris: clip-path circle, 0.15 s shut on A and 0.15 s open on B, over black */
    let clip = "", tf = "", dark = false;
    if (next && outKind === "iris" && dOut < 0.15) { clip = `circle(${(L.EASE.exit(dOut / 0.15) * 120).toFixed(2)}% at 50% 46%)`; dark = true; }
    if (it.i > 0 && inKind === "iris" && dIn < 0.15) { clip = `circle(${(L.EASE.arrive(dIn / 0.15) * 120).toFixed(2)}% at 50% 46%)`; dark = true; }
    /* through: track the target to the centre (0.6 s), then scale it through the frame (0.35 s, strong ease-in) */
    if (next && outKind === "through" && dOut < 0.95 && !LINTING) {
      const h0 = (cur && cur.st && (cur.st.target || cur.st.camHint)) || { x: W / 2, y: H / 2, share: 0.5 };
      const hint = { x: clamp(h0.x, W * 0.2, W * 0.8), y: clamp(h0.y, H * 0.2, H * 0.8), share: h0.share };
      /* the frame must stay covered while the target travels to the centre */
      const cover = Math.max(W / (2 * hint.x), W / (2 * (W - hint.x)), H / (2 * hint.y), H / (2 * (H - hint.y)));
      const tq = L.EASE.camera(1 - seg(dOut, 0.35, 0.95));
      const zq = L.EASE.through(1 - seg(dOut, 0, 0.35));
      const zs = (1 + (cover - 1) * tq) * (1 + (2.5 / clamp(hint.share || 0.5, 0.08, 1) - 1) * zq);
      tf = `translate(${((W / 2 - hint.x) * tq).toFixed(1)}px, ${((H / 2 - hint.y) * tq).toFixed(1)}px) scale(${zs.toFixed(4)})`;
      if (cur) cur.root.style.transformOrigin = `${hint.x.toFixed(0)}px ${hint.y.toFixed(0)}px`;
      blur += zq * 12;
    }
    if (it.i > 0 && inKind === "through") blur += (1 - eo(seg(dIn, 0, 0.13))) * 12;
    /* world: the next scene starts as an object at 8% and scales up until it is the world */
    if (it.i > 0 && inKind === "world" && dIn < 0.35 && !LINTING) {
      const zq = L.EASE.through(seg(dIn, 0, 0.35));
      tf = `scale(${(0.08 + 0.92 * zq).toFixed(4)})`;
      if (cur) cur.root.style.transformOrigin = "50% 46%";
      dark = true;
    }
    layers.scenes.style.background = dark ? "#000" : "";
    if (cur) {
      cur.root.style.clipPath = clip;
      cur.root.style.opacity = o;
      cur.root.style.filter = ((blur > 0.05 ? `blur(${blur.toFixed(2)}px) ` : "") + (camFilter || "")).trim();
      cur.root.style.transform = tf || (!LINTING && (Math.abs(ry) > 0.01 || Math.abs(sc - 1) > 1e-4) ? `perspective(1400px) rotateY(${ry.toFixed(2)}deg) scale(${sc.toFixed(4)})` : "");
      if (!tf) cur.root.style.transformOrigin = "";
    }
    // fade the whole film out at the very end
    /* (not when the last scene loops back to the hook: its last frame leads into the first) */
    const fo = items[items.length - 1].c.loops ? 0 : ei(seg(t, DUR - 0.6, DUR));
    layers.fade.style.opacity = fo;
    layers.fade.style.visibility = fo > 0 ? "visible" : "hidden";
  }

  /* the hook's type slams at t = 0 (it is already fully on screen: frame 0 stays full) */
  const HOOK_SPRING = { stiffness: 140, mass: 1, damping: 19 };
  const SLAM = { stiffness: 320, mass: 1, damping: 25 };
  function hookSlam(s, it, lt) {
    if (it.i !== 0 || !it.c.lively || it.c.p.hook_motion === false || LINTING) return;
    const st = s.st, tgt = st.tb || (st.T && st.T.tb) || st.box || st.b;
    if (tgt && lt < 1) { tgt.style.transformOrigin = "50% 50%"; tgt.style.transform = lt < 0.9 ? `scale(${(1.14 - 0.14 * L.spring(lt, SLAM)).toFixed(4)})` : ""; }
    const h = st.heroes && st.heroes[0];
    if (h && lt < 1) h.node.style.transform += ` scale(${(1 + 0.06 * L.punch(lt + 0.04, 13, 6)).toFixed(4)})`;
  }

  async function renderAt(t) {
    t = clamp(t, 0, DUR - 1e-6);
    const it = items.find((q) => t >= q.t0 && t < q.t1) || items[items.length - 1];
    const s = activate(it);
    /* the hook's first frame must already be full: skip its entrances (the first frame sells the video) */
    const lt = (t - it.t0) * it.c.ts;
    withAccent(it.c, s.root, () => s.def.update(s.st, warp(it.c, lt), it.c));
    carryAt(s, lt);
    hookSlam(s, it, lt);
    if (it.c.accent) { layers.caps.style.setProperty("--accent", it.c.accent); layers.flood.style.background = it.c.accent; }
    else { layers.caps.style.removeProperty("--accent"); layers.flood.style.background = L.C.accent; }
    drawHud(t, it);
    drawCaption(t, it);
    const camFilter = drawCamera(t, it, lt, s);
    drawTransitions(t, it, lt, camFilter);
    drawOverlap(t, it);
    const f = Math.round(t * L.FPS);
    layers.grain.style.backgroundImage = `url(${L.grainTiles()[f % 6]})`;
    layers.grain.style.backgroundPosition = `${(f * 37) % 220}px ${(f * 73) % 220}px`;
    L.zapSeed(f);
    const p = L.pending.splice(0);
    if (p.length) await Promise.all(p);
    return true;
  }

  /* Sound cues for the whole film. A scene cue may carry lvl (1 = rich only,
     2 = standard, 3 = minimal / big moments; default 2): the sfx density
     (timeline.sfx, or a scene's params.sfx) drops cues below its level.
     Swishes may start up to 0.15 s before their scene: they lead the motion. */
  const ALIAS = { swoosh: "swish", rise: "swish" };
  const TRANS_CUES = {
    wipe: [[-0.34, "wipe", 2]],
    zoom: [[-0.42, "whoosh", 2], [0, "flash", 2], [0, "impact", 3]],
    flash: [[0, "flash", 2], [0, "hit", 3]],
    defocus: [[-0.32, "whoosh", 2]],
    flip: [[-0.38, "swish", 2]],
    flood: [[-0.2, "whoosh", 2]],
    dip: [[0, "hit", 2]],
    iris: [[-0.15, "swish", 2]],
    through: [[-0.35, "whoosh", 2], [0, "impact", 3]],
    world: [[0, "whoosh", 2]],
    match: [[-0.05, "swish", 2], [0.42, "pop", 1]],
  };
  function cues() {
    const out = [];
    for (const it of items) {
      const def = window.SCENES[it.type];
      const lvl = L.sfxLevel(it.c);
      const cs = (def.cues ? def.cues(it.c) : []).concat(it.c.p.cues || []);
      for (const q of cs) {
        if ((q.lvl != null ? q.lvl : 2) < lvl) continue;
        const tt = it.t0 + q.lt / it.c.ts;
        if (tt >= it.t0 - 0.15 && tt < it.t1) out.push({ t: +Math.max(0, tt).toFixed(4), type: ALIAS[q.type] || q.type, len: q.len ? q.len / it.c.ts : undefined, lvl: q.lvl, scene: it.id });
      }
      if (it.i === 0 && it.c.lively && it.c.p.hook_motion !== false && !cs.some((q) => q.lt < 0.05 && q.type === "impact") && 3 >= lvl) out.push({ t: 0, type: "impact", lvl: 3, scene: it.id });
      if (it.i > 0) for (const [dt, type, lv] of TRANS_CUES[it.transition] || []) if (lv >= lvl) out.push({ t: +(it.t0 + dt).toFixed(4), type, lvl: lv, scene: it.id });
      /* fast camera moves */
      for (const q of L.rig.cues(it.c)) if (q.lvl >= lvl) out.push({ t: +Math.max(0, it.t0 + q.lt / it.c.ts).toFixed(4), type: q.type, len: q.len, lvl: q.lvl, scene: it.id, cam: true });
    }
    return out.sort((a, b) => a.t - b.t);
  }

  /* Legibility lint at time t: text that leaves the stage or the safe area,
     text clipped by its own box, and text smaller than the platform minimum. */
  async function lint(t, minPx) {
    /* lint the layout, not the transition: transition scale / flip are off while linting */
    LINTING = true;
    try { await renderAt(t); } finally { LINTING = false; }
    dropGhost();
    const issues = [];
    const sb = stage.getBoundingClientRect();
    const scale = sb.width / W;
    const it = items.find((q) => t >= q.t0 && t < q.t1) || items[items.length - 1];
    const sf = it.c.safe;
    const min = minPx || (TL.legibility && TL.legibility.min_px) || 22;
    const nodes = [...layers.scenes.querySelectorAll("*")].filter((e) => {
      if (e.closest(".win") || e.closest("svg") || e.closest("[data-nolint]")) return false;
      const own = [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      if (!own) return false;
      const cs = getComputedStyle(e);
      let p = e; while (p && p !== stage) { const s = getComputedStyle(p); if (s.visibility === "hidden" || +s.opacity < 0.5 || s.display === "none") return false; p = p.parentElement; }
      return cs.visibility !== "hidden";
    });
    for (const e of nodes) {
      const r = e.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      /* an inline span's box is its font box, taller than its line (the accent word in a headline
         would stick out of the safe area by a few px): measure inline text by its parent's line box */
      const vb = getComputedStyle(e).display === "inline" && e.parentElement ? e.parentElement.getBoundingClientRect() : r;
      const x = (r.left - sb.left) / scale, y = (vb.top - sb.top) / scale, w = r.width / scale, h = vb.height / scale;
      const text = e.textContent.trim().slice(0, 60);
      const fs = parseFloat(getComputedStyle(e).fontSize);
      const tf = e.closest("[data-free]") ? null : true;
      if (x < -1 || y < -1 || x + w > W + 1 || y + h > H + 1) issues.push({ scene: it.id, t, kind: "off-stage", text, box: [x, y, w, h].map(Math.round) });
      else if (tf && (x < sf.x - 2 || y < sf.y - 2 || x + w > sf.x + sf.w + 2 || y + h > sf.y + sf.h + 2)) issues.push({ scene: it.id, t, kind: "outside-safe-area", text, box: [x, y, w, h].map(Math.round) });
      if (e.scrollWidth > e.clientWidth + 2 && getComputedStyle(e).overflow !== "visible") issues.push({ scene: it.id, t, kind: "clipped", text });
      if (fs < min) issues.push({ scene: it.id, t, kind: "too-small", text, px: Math.round(fs) });
      /* action-safe 90% / title-safe 80%: advisory, the platform's safe area above is the hard rule */
      if (tf && (x < W * 0.05 - 2 || y < H * 0.05 - 2 || x + w > W * 0.95 + 2 || y + h > H * 0.95 + 2)) issues.push({ scene: it.id, t, kind: "outside-action-safe", severity: "warn", text, box: [x, y, w, h].map(Math.round) });
      else if (tf && fs >= 72 * it.c.u && (y < H * 0.1 - 2 || y + h > H * 0.9 + 2)) issues.push({ scene: it.id, t, kind: "outside-title-safe", severity: "warn", text, box: [x, y, w, h].map(Math.round) });
    }
    /* overlap: free text ([data-lb], laid out by the scene) against other free text and against item shapes */
    const toStage = (e) => { const r = e.getBoundingClientRect(); return { x: (r.left - sb.left) / scale, y: (r.top - sb.top) / scale, w: r.width / scale, h: r.height / scale }; };
    const free = [...layers.scenes.querySelectorAll("[data-lb]")].filter((e) => getComputedStyle(e).visibility !== "hidden" && +getComputedStyle(e).opacity >= 0.5);
    const cards = [...layers.scenes.querySelectorAll(".fv-card")].filter((e) => getComputedStyle(e).visibility !== "hidden" && +getComputedStyle(e).opacity >= 0.5);
    free.forEach((e, i) => {
      const a = toStage(e), text = e.textContent.trim().slice(0, 60);
      for (const f of free.slice(i + 1)) {
        const b = toStage(f);
        if (a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y) issues.push({ scene: it.id, t, kind: "text-overlap", text, with: f.textContent.trim().slice(0, 40) });
      }
      if (e.dataset.lb === "over") return; /* a title on its own paper strips may sit on the subject */
      for (const n of cards) {
        const occ = n._occ, b = toStage(n);
        let hits = 0, all = 0;
        for (let v = 0.1; v < 1; v += 0.2) for (let u = 0.05; u < 1; u += 0.1) {
          const px = a.x + a.w * u, py = a.y + a.h * v;
          all++;
          if (occ ? occ(px, py) : px > b.x && px < b.x + b.w && py > b.y && py < b.y + b.h) hits++;
        }
        if (hits / all > 0.06) { issues.push({ scene: it.id, t, kind: "text-over-item", text }); break; }
      }
    });
    return issues;
  }

  window.STAGE = { init, renderAt, cues, lint, info: () => info(), items: () => items.map((q) => ({ id: q.id, type: q.type, t0: q.t0, t1: q.t1 })) };
})();
