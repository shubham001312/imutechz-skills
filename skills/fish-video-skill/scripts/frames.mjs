/* Render the stage frame by frame and encode a silent intermediate.

     node scripts/frames.mjs <project> --platform youtube [--workers 4] [--scale 1]
                             [--from 0 --to 10] [--info-only] [--crf 16]

   1. opens scripts/stage/index.html?p=<platform> in headless Chromium and
      writes <project>/build/<platform>/info.json: duration, chapters, every
      sound cue the scenes export (music.mjs reads it)
   2. renders frames t = n / fps in parallel workers; each worker pipes PNG
      screenshots into its own ffmpeg (x264, CRF 16, yuv420p)
   3. concatenates the segments into build/<platform>/video.mp4

   Rendering is deterministic: STAGE.renderAt(t) is a pure function of t,
   so workers can split the range arbitrarily and a re-render is identical.
   --scale 0.5 renders at half resolution (deviceScaleFactor) for previews
   and tests, with an identical layout. */
import fs from "node:fs";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { launch, serve, ffmpegPath, parseArgs, writeJSON, main, isMain, safeWorkers } from "./common.mjs";

export async function openStage(browser, url, platform, W, H, scale = 1) {
  const p = await browser.newPage();
  const errors = [];
  p.on("pageerror", (e) => { errors.push(e.message); console.log("  pageerror:", e.message); });
  p.on("console", (m) => { if (m.type() === "error") { errors.push(m.text()); console.log("  console:", m.text().slice(0, 200)); } });
  /* layout always at design size; --scale shrinks the screenshot (clip.scale), not the layout */
  await p.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
  await p.goto(`${url}/skill/scripts/stage/index.html?p=${encodeURIComponent(platform)}`, { waitUntil: "load" });
  const info = await p.evaluate(() => window.STAGE.init());
  return { p, info, errors };
}

/** Read W/H from the timeline so the viewport matches before init. */
export function timelineSize(project, platform) {
  const tl = JSON.parse(fs.readFileSync(path.join(project, "build", `timeline-${platform}.json`), "utf8"));
  return { W: tl.W, H: tl.H, fps: tl.fps || 30, tl };
}

/* A browser can die mid-render (memory, a killed process). The frames are a pure function
   of t, so redo just that worker's segment rather than losing the whole render. */
async function workerRetry(k, a, b, ctx, tries = 5) {
  for (let n = 1; ; n++) {
    try { return await worker(k, a, b, ctx); }
    catch (e) {
      const m = String(e && e.message);
      if (n >= tries || !/Target closed|Protocol error|Connection closed|Session closed|detached|ffmpeg exited|EPIPE/i.test(m)) throw e;
      console.log(`  w${k}: browser lost (${m.slice(0, 80)}); retry ${n}/${tries - 1}`);
      await new Promise((r) => setTimeout(r, 1500 * n));          /* let the dead browser's memory come back before the next one starts */
    }
  }
}

async function worker(k, a, b, ctx) {
  const { url, platform, W, H, scale, fps, outDir, crf } = ctx;
  const browser = await launch();
  let ff = null, finished = false;
  try {
    const { p } = await openStage(browser, url, platform, W, H, scale);
    const cdp = await p.createCDPSession();
    const seg = path.join(outDir, `seg${k}.mp4`);
    ff = spawn(ffmpegPath(), ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "png", "-i", "-",
      "-c:v", "libx264", "-threads", "2", "-preset", ctx.preset, "-crf", String(crf), "-pix_fmt", "yuv420p", "-r", String(fps), seg], { stdio: ["pipe", "inherit", "inherit"] });
    const done = new Promise((r, j) => { ff.on("close", (c) => (c === 0 ? r() : j(new Error(`ffmpeg exited ${c} (worker ${k})`)))); ff.on("error", j); });
    done.catch(() => { /* handled where it is awaited; a killed ffmpeg must not become an unhandled rejection */ });
    ff.stdin.on("error", () => { /* surfaced by `done` */ });
    const t0 = Date.now();
    for (let f = a; f < b; f++) {
      await p.evaluate((t) => window.STAGE.renderAt(t), f / fps);
      const { data } = await cdp.send("Page.captureScreenshot", { format: "png", optimizeForSpeed: true, ...(scale !== 1 ? { clip: { x: 0, y: 0, width: W, height: H, scale } } : {}) });
      if (!ff.stdin.write(Buffer.from(data, "base64"))) await new Promise((r) => ff.stdin.once("drain", r));
      if ((f - a) % 150 === 0) console.log(`  w${k}: ${f - a}/${b - a} (${((Date.now() - t0) / Math.max(1, f - a)).toFixed(0)} ms/frame)`);
    }
    ff.stdin.end();
    await done;
    finished = true;
    return seg;
  } finally {
    /* a worker that failed (browser lost) must not leave its ffmpeg waiting on a pipe nobody writes: the render would hang after the retry */
    if (ff && !finished) { try { ff.stdin.destroy(); ff.kill("SIGKILL"); } catch { /* already gone */ } }
    await browser.close().catch(() => {});
  }
}

export async function renderFrames(project, opts = {}) {
  const platform = opts.platform || "youtube";
  const { W, H, fps } = timelineSize(project, platform);
  const outDir = path.join(project, "build", platform);
  fs.mkdirSync(outDir, { recursive: true });
  const { srv, url } = await serve(project);
  try {
    const b0 = await launch();
    let info;
    try {
      const st = await openStage(b0, url, platform, W, H, opts.scale || 1);
      info = st.info;
      info.cues = await st.p.evaluate(() => window.STAGE.cues());
      info.scenes = await st.p.evaluate(() => window.STAGE.items());
      info.errors = st.errors;
    } finally { await b0.close(); }
    info.scale = opts.scale || 1;
    writeJSON(path.join(outDir, "info.json"), info);
    console.log(`${platform}: ${info.duration}s, ${info.frames} frames, ${info.cues.length} cues`);
    if (opts.infoOnly) return { info };

    const F0 = Math.round((opts.from || 0) * fps);
    const F1 = Math.min(info.frames, Math.round((opts.to != null ? opts.to : info.duration) * fps));
    const n = F1 - F0, workers = Math.max(1, Math.min(safeWorkers(opts.workers || 4), Math.ceil(n / 30)));
    const per = Math.ceil(n / workers);
    const ctx = { url, platform, W, H, scale: opts.scale || 1, fps, outDir, crf: opts.crf || 16, preset: opts.preset || "medium" };
    const t0 = Date.now();
    const jobs = [];
    for (let k = 0; k < workers; k++) { const a = F0 + k * per, b = Math.min(F1, a + per); if (a < b) jobs.push(workerRetry(k, a, b, ctx)); }
    const segs = await Promise.all(jobs);
    const list = path.join(outDir, "segs.txt");
    fs.writeFileSync(list, segs.map((s) => `file '${s.replace(/\\/g, "/")}'`).join("\n"));
    const video = path.join(outDir, opts.from || opts.to != null ? "video-preview.mp4" : "video.mp4");
    const r = spawnSync(ffmpegPath(), ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-c", "copy", video], { stdio: "inherit" });
    if (r.status !== 0) throw new Error("ffmpeg concat failed");
    for (const s of segs) fs.rmSync(s, { force: true });
    console.log(`frames done in ${((Date.now() - t0) / 1000).toFixed(0)} s -> ${video}`);
    return { info, video, from: F0 / fps, to: F1 / fps };
  } finally {
    srv.close();
  }
}

if (isMain(import.meta.url)) main(async () => {
  const a = parseArgs();
  if (!a._[0]) throw new Error("usage: node scripts/frames.mjs <project> --platform youtube [--workers 4] [--scale 1] [--from s --to s] [--info-only]");
  const r = await renderFrames(a._[0], {
    platform: a.platform || "youtube", workers: +(a.workers || 4), scale: +(a.scale || 1),
    from: a.from != null ? +a.from : 0, to: a.to != null ? +a.to : undefined, infoOnly: !!a["info-only"], crf: a.crf ? +a.crf : 16, preset: a.preset,
  });
  console.log(JSON.stringify({ video: r.video || null, duration: r.info.duration, errors: r.info.errors.length }));
});
