/* Design probe: render stills and report the text that is on them.

     node scripts/designprobe.mjs <project> --platform youtube --scenes [--k 0.8] [--scene id,id]
     node scripts/designprobe.mjs <project> --platform youtube --at 1.5,8
     options: --out dir (default build/<platform>/design)  --scale 1  --mode lint|render

   For each time it renders the frame, takes a screenshot and walks the stage's DOM for every
   visible text element: its words, box, font size and weight, and declared colour. design.py
   and thumbs.py measure the pixels behind those boxes (contrast, hierarchy, legibility).

   --mode lint (default) renders through STAGE.lint, so transition scale and flips are off and
   the stage's own legibility issues come back with the probe. --mode render is the frame as the
   viewer sees it. The same elements the stage lint skips are skipped here: text inside a
   captured browser window, inside an SVG, and inside [data-nolint] chrome.
   Output: <out>/probe.json and one JSON line on stdout. */
import fs from "node:fs";
import path from "node:path";
import { launch, serve, parseArgs, writeJSON, main, isMain } from "./common.mjs";
import { openStage, timelineSize } from "./frames.mjs";

/* runs in the page: boxes of [data-tile] elements (thumbnail tiles) and of [data-block] chips */
function collectBlocks() {
  const stage = document.getElementById("stage"), sb = stage.getBoundingClientRect();
  const W = parseFloat(stage.style.width) || sb.width, scale = sb.width / W;
  return [...document.querySelectorAll("#scenes [data-block]")].map((e) => { const r = e.getBoundingClientRect(); return { name: e.dataset.block, box: [(r.left - sb.left) / scale, (r.top - sb.top) / scale, r.width / scale, r.height / scale].map((v) => Math.round(v * 10) / 10) }; });
}
function collectTiles() {
  const stage = document.getElementById("stage"), sb = stage.getBoundingClientRect();
  const W = parseFloat(stage.style.width) || sb.width, scale = sb.width / W;
  return [...document.querySelectorAll("#scenes [data-tile]")].map((e) => { const r = e.getBoundingClientRect(); return [(r.left - sb.left) / scale, (r.top - sb.top) / scale, r.width / scale, r.height / scale].map((v) => Math.round(v * 10) / 10); });
}
/* runs in the page */
function collect() {
  const stage = document.getElementById("stage"), scenes = document.getElementById("scenes");
  const sb = stage.getBoundingClientRect();
  const W = parseFloat(stage.style.width) || sb.width, scale = sb.width / W;
  const shown = (e) => {
    let p = e;
    while (p && p !== stage) { const s = getComputedStyle(p); if (s.visibility === "hidden" || s.display === "none" || +s.opacity < 0.5) return false; p = p.parentElement; }
    return true;
  };
  const out = [];
  for (const e of scenes.querySelectorAll("*")) {
    if (e.closest(".win") || e.closest("svg") || e.closest("[data-nolint]")) continue;
    const own = [...e.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own.length || !shown(e)) continue;
    /* the box of the words themselves, not of a block that is wider than its text */
    const rg = document.createRange();
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of own) {
      rg.selectNodeContents(n);
      for (const r of rg.getClientRects()) { if (r.width < 1 || r.height < 1) continue; x0 = Math.min(x0, r.left); y0 = Math.min(y0, r.top); x1 = Math.max(x1, r.right); y1 = Math.max(y1, r.bottom); }
    }
    if (!(x1 > x0 && y1 > y0)) continue;
    const cs = getComputedStyle(e);
    out.push({
      text: own.map((n) => n.textContent.trim()).join(" ").replace(/\s+/g, " ").slice(0, 80),
      words: own.map((n) => n.textContent.trim()).join(" ").split(/\s+/).filter(Boolean).length,
      box: [(x0 - sb.left) / scale, (y0 - sb.top) / scale, (x1 - x0) / scale, (y1 - y0) / scale].map((v) => Math.round(v * 10) / 10),
      px: Math.round(parseFloat(cs.fontSize) * 10) / 10,
      weight: +cs.fontWeight || 400,
      color: cs.webkitTextFillColor && cs.webkitTextFillColor !== cs.color ? cs.webkitTextFillColor : cs.color,
      family: cs.fontFamily.split(",")[0].replace(/["']/g, "").trim(),
      upper: cs.textTransform === "uppercase",
      free: !!e.closest("[data-free]"),
      grp: (e.closest("[data-grp]") || { dataset: {} }).dataset.grp || "",
    });
  }
  return out;
}

if (isMain(import.meta.url)) main(async () => {
  const a = parseArgs();
  const project = a._[0];
  if (!project) throw new Error("usage: node scripts/designprobe.mjs <project> --platform p (--scenes | --at t,t)");
  const platform = a.platform || "youtube";
  const mode = a.mode === "render" ? "render" : "lint";
  const sc = +(a.scale || 1), k = a.k != null ? +a.k : 0.8;
  const { W, H } = timelineSize(project, platform);
  const outDir = a.out || path.join(project, "build", platform, "design");
  fs.mkdirSync(outDir, { recursive: true });
  const { srv, url } = await serve(project);
  const b = await launch();
  try {
    const { p, errors } = await openStage(b, url, platform, W, H, sc);
    const items = await p.evaluate(() => window.STAGE.items());
    const want = a.scene ? new Set(String(a.scene).split(",")) : null;
    let shots;
    if (a.at != null && a.at !== true) shots = String(a.at).split(",").map(Number).map((t) => { const it = items.find((q) => t >= q.t0 && t < q.t1) || items[items.length - 1]; return { t, id: it.id, type: it.type, t0: it.t0, t1: it.t1 }; });
    else shots = items.filter((it) => !want || want.has(it.id)).map((it) => ({ t: +(it.t0 + (it.t1 - it.t0) * k).toFixed(3), id: it.id, type: it.type, t0: it.t0, t1: it.t1 }));
    if (want && !shots.length) throw new Error(`no scene named ${[...want].join(", ")} (scenes: ${items.map((q) => q.id).join(", ")})`);
    const frames = [];
    for (const s of shots) {
      let issues = [];
      if (mode === "lint") issues = await p.evaluate((t) => window.STAGE.lint(t), s.t);
      else await p.evaluate((t) => window.STAGE.renderAt(t), s.t);
      const texts = await p.evaluate(collect);
      const tiles = await p.evaluate(collectTiles);
      const blocks = await p.evaluate(collectBlocks);
      const file = path.join(outDir, `${String(s.id).replace(/[^\w.-]+/g, "_")}-${s.t.toFixed(2)}.png`);
      await p.screenshot({ path: file, ...(sc !== 1 ? { clip: { x: 0, y: 0, width: W, height: H, scale: sc } } : {}) });
      frames.push({ scene: s.id, type: s.type, t: s.t, t0: s.t0, t1: s.t1, file, texts, tiles, blocks, issues });
    }
    const rep = { platform, W, H, scale: sc, mode, frames, errors };
    writeJSON(path.join(outDir, "probe.json"), rep);
    console.log(JSON.stringify({ probe: path.join(outDir, "probe.json"), frames: frames.length, errors: errors.length }));
  } finally {
    await b.close();
    srv.close();
  }
});
