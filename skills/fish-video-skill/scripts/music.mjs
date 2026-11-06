/* Original score + sound design, synthesised from scratch (no samples,
   no downloads, no licensing questions).

     node scripts/music.mjs <project> --platform youtube [--out file.wav]

   Reads <project>/build/<platform>/info.json (tempo, bars, the energy map,
   every sound cue; written by frames.mjs) and the score settings in
   timeline-<platform>.json (`score`: key, mode, progression, seed).

   Default: 120 BPM, D minor, i-VI-III-VII (Dm9 - Bbmaj7 - Fmaj7 - Cadd9).
   Layers: kick, clap, hats, shaker, sub bass, detuned-saw pads, a delayed
   pluck arpeggio, a bell motif; risers, impacts and drum fills at section
   changes; a kick sidechain; a Freeverb-style room. Energy per bar
   (0 calm .. 3 full) comes from the storyboard. UI sounds (clicks, keys,
   whooshes, pops, marker scribbles, chimes) are placed from the cue list.
   Output: 48 kHz stereo float WAV, normalised later by render.py. */
import fs from "node:fs";
import path from "node:path";
import { parseArgs, isMain } from "./common.mjs";
import { buildProgression, NOTE, SCALES, planSections, sectionSig, sigKey, arpPattern, bassPattern } from "./harmony.mjs";

const args = parseArgs();
const project = args._[0];
const platform = args.platform || "youtube";
if (!project && isMain(import.meta.url)) { console.error("usage: node scripts/music.mjs <project> --platform youtube"); process.exit(2); }
const info = JSON.parse(fs.readFileSync(path.join(project, "build", platform, "info.json"), "utf8"));
const tl = JSON.parse(fs.readFileSync(path.join(project, "build", `timeline-${platform}.json`), "utf8"));
const score = Object.assign({ key: "D", mode: "minor", progression: "i-VI-III-VII", seed: 12345, sfx: true, drums: true, palette: {} }, tl.score || {});

const SR = 48000;
const BPM = info.bpm, BEAT = 60 / BPM, BAR = BEAT * 4;
const DUR = info.duration + 1.5; // let the tail ring
const N = Math.ceil(DUR * SR);
const TAU = Math.PI * 2;

/* buses (stereo) */
const bus = () => [new Float32Array(N), new Float32Array(N)];
const drums = bus(), bass = bus(), pads = bus(), keys = bus(), sfx = bus(), send = bus(), mfx = bus();
const duck = new Float32Array(N).fill(1);

let seed = (score.seed >>> 0) || 12345;
const rnd = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296);
const noise = () => rnd() * 2 - 1;
const mtof = (m) => 440 * Math.pow(2, (m - 69) / 12);
const panLR = (p) => [Math.cos((p + 1) * Math.PI / 4), Math.sin((p + 1) * Math.PI / 4)];

function add(b, i, l, r) { if (i >= 0 && i < N) { b[0][i] += l; b[1][i] += r; } }

/* energy per bar */
const BARS = Math.ceil(info.bars);   // Shorts cut on beats, so a scene may end mid-bar
const energy = new Array(BARS + 2).fill(0);
{
  const m = info.music;
  for (let k = 0; k < m.length; k++) {
    const b0 = Math.round(m[k][0]), e = m[k][1];      // scenes follow the narration, so a section starts on the nearest bar
    const b1 = Math.round(k + 1 < m.length ? m[k + 1][0] : BARS);
    for (let b = b0; b < b1; b++) energy[b] = e;
  }
  energy[BARS] = -1;
}

/* sections + the bars under a key line (a reveal or punchline: the bed thins so the words land) */
const SEC = planSections(energy, BARS, 8);
const PAL = score.palette || {};
const SIGS = SEC.map((i) => sectionSig(i, PAL));
const KEYBARS = new Set(((tl.voice_lines || []).filter((l) => /^(reveal|punchline)$/.test(l.tag || "")).map((l) => Math.floor(l.at / (60 / info.bpm * 4)))));
const sections = [...new Set(SEC)].map((i) => ({ section: i, from_bar: SEC.indexOf(i), sig: sigKey(SIGS[SEC.indexOf(i)]) }));

/* ------------------------------------------------------------- harmony */
const PROG = buildProgression(score.key, score.mode, score.progression);
const chordAt = (bar) => { const sg = SIGS[bar] || SIGS[SIGS.length - 1] || { rot: 0 }; return PROG[(((bar + sg.rot) % PROG.length) + PROG.length) % PROG.length]; };

/* ------------------------------------------------------------- voices */
function kick(t0, g = 1) {
  const i0 = Math.round(t0 * SR), n = Math.round(0.45 * SR);
  let ph = 0;
  for (let k = 0; k < n; k++) {
    const t = k / SR;
    const f = 46 + 110 * Math.exp(-t / 0.045);
    ph += TAU * f / SR;
    const a = Math.exp(-t / 0.22) * (t < 0.002 ? t / 0.002 : 1);
    let s = Math.sin(ph) * a * 0.95;
    if (k < 240) s += noise() * 0.25 * (1 - k / 240);
    s = Math.tanh(s * 1.4) * g;
    add(drums, i0 + k, s, s);
  }
  // sidechain
  const m = Math.round(0.32 * SR);
  for (let k = 0; k < m; k++) { const i = i0 + k; if (i < N) duck[i] = Math.min(duck[i], 1 - 0.62 * g * Math.exp(-k / SR / 0.11)); }
}
function clap(t0, g = 1) {
  const i0 = Math.round(t0 * SR), n = Math.round(0.32 * SR);
  let bp1 = 0, bp2 = 0, lp = 0;
  for (let k = 0; k < n; k++) {
    const t = k / SR;
    let env = 0;
    for (const o of [0, 0.011, 0.022]) if (t >= o) env = Math.max(env, Math.exp(-(t - o) / (o === 0.022 ? 0.11 : 0.012)));
    // crude band-pass ~1.5 kHz
    const x = noise();
    lp += 0.35 * (x - lp);
    bp1 = x - lp;
    bp2 += 0.5 * (bp1 - bp2);
    const s = bp2 * env * 0.7 * g + Math.sin(TAU * 185 * t) * Math.exp(-t / 0.04) * 0.25 * g;
    add(drums, i0 + k, s * 0.9, s);
    add(send, i0 + k, s * 0.25, s * 0.25);
  }
}
function hat(t0, g = 1, open = false, pan = 0.2) {
  const i0 = Math.round(t0 * SR), dec = open ? 0.2 : 0.035, n = Math.round((open ? 0.45 : 0.09) * SR);
  let lp = 0, prev = 0;
  const [pl, pr] = panLR(pan);
  for (let k = 0; k < n; k++) {
    const x = noise();
    lp += 0.6 * (x - lp);
    const hp = x - lp;
    const h2 = hp - prev * 0.5; prev = hp;
    const s = h2 * Math.exp(-(k / SR) / dec) * 0.22 * g;
    add(drums, i0 + k, s * pl, s * pr);
  }
}
function shaker(t0, g = 1) {
  const i0 = Math.round(t0 * SR), n = Math.round(0.07 * SR);
  let lp = 0;
  for (let k = 0; k < n; k++) {
    const t = k / SR;
    const x = noise(); lp += 0.45 * (x - lp);
    const s = (x - lp) * Math.sin(Math.PI * t / 0.07) * 0.09 * g;
    add(drums, i0 + k, s * 0.7, s);
  }
}
function bassNote(t0, dur, m, g = 1) {
  const i0 = Math.round(t0 * SR), n = Math.round((dur + 0.05) * SR);
  const f = mtof(m);
  let ph = 0, lp = 0;
  for (let k = 0; k < n; k++) {
    const t = k / SR;
    ph += TAU * f / SR;
    const a = Math.min(1, t / 0.006) * (t < dur ? 1 : Math.exp(-(t - dur) / 0.02)) * (0.75 + 0.25 * Math.exp(-t / 0.15));
    let s = Math.sin(ph) + 0.35 * Math.sin(2 * ph) + 0.12 * Math.sin(3 * ph);
    s = Math.tanh(s * 1.3);
    lp += 0.18 * (s - lp);
    const v = lp * a * 0.42 * g;
    add(bass, i0 + k, v, v);
  }
}
function polyblep(t, dt) {
  if (t < dt) { t /= dt; return t + t - t * t - 1; }
  if (t > 1 - dt) { t = (t - 1) / dt; return t * t + t + t + 1; }
  return 0;
}
function padChord(t0, dur, notes, g = 1, bright = 0.5) {
  const i0 = Math.round(t0 * SR), rel = 0.9, n = Math.round((dur + rel) * SR);
  const vo = [];
  notes.forEach((m, j) => { for (const d of [-0.09, 0.07, 0.0]) vo.push({ f: mtof(m) * Math.pow(2, d / 12), ph: rnd(), pan: ((j % 2) ? 1 : -1) * (0.25 + 0.4 * Math.abs(d) * 5) }); });
  let l1 = [0, 0], l2 = [0, 0];
  const cut = 0.035 + 0.06 * bright;
  for (let k = 0; k < n; k++) {
    const t = k / SR;
    let L0 = 0, R0 = 0;
    for (const v of vo) {
      const dt = v.f / SR;
      v.ph += dt; if (v.ph >= 1) v.ph -= 1;
      const s = (2 * v.ph - 1) - polyblep(v.ph, dt);
      const [pl, pr] = panLR(v.pan);
      L0 += s * pl; R0 += s * pr;
    }
    const lfo = 1 + 0.25 * Math.sin(TAU * 0.11 * (t0 + t));
    const c = cut * lfo;
    l1[0] += c * (L0 - l1[0]); l1[1] += c * (R0 - l1[1]);
    l2[0] += c * (l1[0] - l2[0]); l2[1] += c * (l1[1] - l2[1]);
    const a = Math.min(1, t / 0.6) * (t < dur ? 1 : Math.exp(-(t - dur) / 0.35));
    const v0 = l2[0] * a * 0.055 * g, v1 = l2[1] * a * 0.055 * g;
    add(pads, i0 + k, v0, v1);
    add(send, i0 + k, v0 * 0.5, v1 * 0.5);
  }
}
function pluck(t0, m, g = 1, pan = 0) {
  const i0 = Math.round(t0 * SR), n = Math.round(0.6 * SR);
  const f = mtof(m);
  const [pl, pr] = panLR(pan);
  let ph = 0, lp = 0;
  for (let k = 0; k < n; k++) {
    const t = k / SR;
    ph += f / SR; if (ph >= 1) ph -= 1;
    const tri = 1 - 4 * Math.abs(ph - 0.5);
    const sq = ph < 0.5 ? 1 : -1;
    const x = tri * 0.7 + sq * 0.3;
    lp += (0.08 + 0.5 * Math.exp(-t / 0.03)) * (x - lp);
    const s = lp * Math.exp(-t / 0.16) * Math.min(1, t / 0.002) * 0.16 * g;
    add(keys, i0 + k, s * pl, s * pr);
    add(send, i0 + k, s * 0.3, s * 0.3);
    // dotted-eighth ping-pong delay
    for (let r = 1; r <= 3; r++) {
      const d = Math.round(r * BEAT * 0.75 * SR);
      const fb = Math.pow(0.38, r);
      if (r % 2) add(keys, i0 + k + d, s * fb * 0.2, s * fb);
      else add(keys, i0 + k + d, s * fb, s * fb * 0.2);
    }
  }
}
function bell(t0, m, g = 1, pan = 0) {
  const i0 = Math.round(t0 * SR), n = Math.round(1.8 * SR);
  const f = mtof(m);
  const [pl, pr] = panLR(pan);
  for (let k = 0; k < n; k++) {
    const t = k / SR;
    const mod = Math.sin(TAU * f * 3.5 * t) * 1.6 * Math.exp(-t / 0.25);
    const s = Math.sin(TAU * f * t + mod) * Math.exp(-t / 0.55) * Math.min(1, t / 0.003) * 0.11 * g;
    add(keys, i0 + k, s * pl, s * pr);
    add(send, i0 + k, s * 0.6, s * 0.6);
  }
}
function riser(t0, dur, g = 1, B = sfx) {
  const i0 = Math.round(t0 * SR), n = Math.round(dur * SR);
  let lp = 0, bp = 0;
  for (let k = 0; k < n; k++) {
    const p = k / n;
    const x = noise();
    const c = 0.02 + 0.5 * p * p;
    lp += c * (x - lp); bp += c * (lp - bp);
    const s = (lp - bp) * Math.pow(p, 2.2) * 0.5 * g + Math.sin(TAU * (200 + 900 * p * p) * (k / SR)) * Math.pow(p, 3) * 0.04 * g;
    const pan = Math.sin(p * 9) * 0.5;
    const [pl, pr] = panLR(pan);
    add(B, i0 + k, s * pl, s * pr);
    if (B !== sfx) add(send, i0 + k, s * 0.4, s * 0.4);
  }
}
function impact(t0, g = 1, B = sfx, tail = 1.6) {
  const i0 = Math.round(t0 * SR), n = Math.round(tail * SR);
  let ph = 0, lp = 0;
  for (let k = 0; k < n; k++) {
    const t = k / SR;
    ph += TAU * (32 + 60 * Math.exp(-t / 0.12)) / SR;
    const x = noise(); lp += 0.08 * (x - lp);
    const s = (Math.sin(ph) * Math.exp(-t / 0.5) * 0.75 + lp * Math.exp(-t / 0.35) * 0.6) * g;
    add(B, i0 + k, s, s);
    if (B !== sfx) add(send, i0 + k, s * 0.5, s * 0.5);
  }
}

/* ------------------------------------------------------------- the arrangement */
for (let bar = 0; bar < BARS; bar++) {
  let e = energy[bar]; const next = energy[bar + 1]; const sg = SIGS[bar] || sectionSig(0, PAL);
  if (KEYBARS.has(bar) && e > 1) e = 1;     // a key line: thin the bed (no drums, light bass) for this bar
  const DS = PAL.drum || "four";
  const t = bar * BAR;
  const ch = chordAt(bar);
  const last = bar === BARS - 1;
  // pads always (end: long ring)
  padChord(t, BAR, ch.notes, e >= 2 ? 0.95 : 0.85, e >= 3 ? 0.9 : e >= 1 ? 0.55 : 0.3);
  // drums
  if (e >= 1 && score.drums !== false) {
    for (let b = 0; b < 4; b++) {
      const tb = t + b * BEAT;
      const kk = DS === "half" ? b === 0 || (e >= 2 && b === 2 && bar % 2) : DS === "broken" ? b === 0 || (b === 2 && e >= 2) || (b === 3 && bar % 2 && e >= 3) : (e >= 2 || b % 2 === 0);
      if (kk) kick(tb, e >= 2 ? 0.95 : 0.6);
      const cl = DS === "half" ? b === 2 : (b === 1 || b === 3);
      if (e >= 2 && cl) clap(tb, e >= 3 ? 0.9 : 0.75);
      hat(tb + BEAT / 2, e >= 2 ? 0.95 : 0.6, e >= 3 && b === 3, 0.25);
      if (e >= 2 && DS !== "half") hat(tb, 0.35, false, -0.2);
      if (e >= 3 && DS !== "half") for (let s = 0; s < 4; s++) shaker(tb + s * BEAT / 4, s % 2 ? 1 : 0.6);
    }
  }
  // bass: syncopated eighths
  if (e >= 2) {
    const pat = bassPattern(sg.bass);
    for (let s = 0; s < 8; s++) if (pat[s]) bassNote(t + s * BEAT / 2, BEAT / 2 * 0.85, ch.root + (s === 6 ? 12 : 0), 1);
  } else if (e === 1) {
    bassNote(t, BEAT * 1.8, ch.root, 0.7);
    bassNote(t + BEAT * 2.5, BEAT * 1.2, ch.root, 0.55);
  }
  // lead: the section's voice plays the section's arpeggio shape
  if (sg.lead !== "none" && e >= 1) {
    const steps = e >= 2 ? 16 : 8;
    const tones = ch.notes.map((m) => m + 12);
    const shape = arpPattern(sg.arp);
    for (let s = 0; s < steps; s++) {
      const idx = shape[s % 8];
      const m = tones[idx % tones.length] + (s >= 8 && e >= 2 ? 12 : 0);
      const pan = ((s % 4) - 1.5) * 0.3;
      if (sg.lead === "bell") { if (s % 2 === 0) bell(t + s * BAR / steps, m, 0.55, pan); }
      else if (sg.lead === "glass") { if (s % 2 === 0) { pluck(t + s * BAR / steps, m + 12, 0.55, pan); bell(t + s * BAR / steps, m, 0.3, -pan); } }
      else pluck(t + s * BAR / steps, m, e >= 3 ? 1 : 0.8, pan);
    }
  } else if (sg.lead !== "none") {
    // calm: a few soft notes
    [0, 1.5, 2.5].forEach((b, j) => pluck(t + b * BEAT, ch.notes[(j * 2) % ch.notes.length] + 12, 0.6, j ? 0.3 : -0.3));
  }
  // bell motif on high energy, every other bar
  if (e >= 3 && bar % 2 === 0) [0, 0.75, 1.5, 2.5].forEach((b, j) => bell(t + b * BEAT, ch.notes[[4, 3, 2, 3][j]] + 24, 0.8, j % 2 ? 0.4 : -0.4));
  // transitions into a bigger section
  if (next > e && next >= 1) {
    riser(t + BAR * 0.25, BAR * 0.75, 0.9, mfx);
    if (e >= 1) for (let s = 0; s < 8; s++) clap(t + BAR / 2 + s * BEAT / 4, 0.25 + 0.5 * (s / 8));
  }
  if (bar > 0 && e > energy[bar - 1] && e >= 2) impact(t, 0.8, mfx);
  /* the outro: a last hit and a falling bell figure where the music drops out */
  if (bar > 0 && e === 0 && energy[bar - 1] > 0) {
    impact(t, 0.7, mfx);
    [0, 7, 12, (score.mode === "major" || score.mode === "mixolydian") ? 16 : 15].map((x) => 74 - 2 + (NOTE[score.key] || 2) + x).forEach((m, j) => bell(t + j * BEAT * 0.5, m, 1 - j * 0.12, j % 2 ? 0.35 : -0.35));
  }
  if (last) padChord(t + BAR, BAR * 0.8, PROG[0].notes, 0.7, 0.25);
}

/* ------------------------------------------------------------- sound effects */
function blip(t0, f0, f1, dur, g, pan = 0, wave = "sine") {
  const i0 = Math.round(t0 * SR), n = Math.round(dur * SR);
  const [pl, pr] = panLR(pan);
  let ph = 0;
  for (let k = 0; k < n; k++) {
    const p = k / n;
    const f = f0 * Math.pow(f1 / f0, p);
    ph += f / SR;
    const x = wave === "sine" ? Math.sin(TAU * ph) : 1 - 4 * Math.abs((ph % 1) - 0.5);
    const s = x * Math.min(1, k / 60) * Math.pow(1 - p, 2.5) * g;
    add(sfx, i0 + k, s * pl, s * pr);
  }
}
function tick(t0, g = 0.25, f = 3200) {
  const i0 = Math.round(t0 * SR), n = Math.round(0.03 * SR);
  let lp = 0;
  for (let k = 0; k < n; k++) {
    const t = k / SR;
    const x = noise(); lp += 0.5 * (x - lp);
    const s = ((x - lp) * Math.exp(-t / 0.004) * 0.6 + Math.sin(TAU * f * t) * Math.exp(-t / 0.008)) * g;
    add(sfx, i0 + k, s, s);
  }
}
function whoosh(t0, dur, g = 0.5) {
  const i0 = Math.round(t0 * SR), n = Math.round(dur * SR);
  let lp = 0, bp = 0;
  for (let k = 0; k < n; k++) {
    const p = k / n;
    const env = Math.pow(Math.sin(Math.PI * p), 1.6);
    const c = 0.03 + 0.25 * Math.sin(Math.PI * p);
    const x = noise(); lp += c * (x - lp); bp += c * (lp - bp);
    const s = (lp - bp) * env * g;
    const [pl, pr] = panLR(-0.8 + 1.6 * p);
    add(sfx, i0 + k, s * pl, s * pr);
    add(send, i0 + k, s * 0.3, s * 0.3);
  }
}
function scribble(t0, dur, g = 0.12) {
  const i0 = Math.round(t0 * SR), n = Math.round(dur * SR);
  let lp = 0, bp = 0, amp = 0;
  const rate = 9 + rnd() * 4;
  for (let k = 0; k < n; k++) {
    const t = k / SR;
    const stroke = 0.5 + 0.5 * Math.sin(TAU * rate * t + Math.sin(TAU * 2.3 * t) * 2);
    amp += 0.002 * (stroke - amp);
    const x = noise(); lp += 0.45 * (x - lp); bp += 0.25 * (lp - bp);
    const s = (lp - bp) * amp * Math.min(1, t / 0.03, (dur - t) / 0.05) * g;
    add(sfx, i0 + k, s * 0.8, s);
  }
}
function key(t0, g = 0.16) {
  const f = 1800 + rnd() * 1400;
  tick(t0, g, f);
  blip(t0, 300 + rnd() * 80, 200, 0.03, g * 0.5);
}
const PENTA = [0, 2, 4, 7, 9, 12].map((x) => 72 + (NOTE[score.key] || 2) + x);
/* density: rich = all cues; standard = drop pops/ticks/blips; minimal = only big moments */
const DENSITY = (tl.sfx && tl.sfx.density) || score.density || "rich";
const SMALL = new Set(["pop", "tick", "tok", "blips", "key", "ripple", "paper"]);
const BIG = new Set(["impact", "hit", "boom", "riser", "swell", "flash", "wipe", "thump"]);
/* cue types that real samples cover (written by sfx.py before this runs) are skipped here */
let COVERED = new Set();
try { COVERED = new Set(JSON.parse(fs.readFileSync(path.join(project, "build", platform, "sfx-covered.json"), "utf8"))); } catch { /* none */ }
function noisebp(t0, dur, f0, f1, g, panFrom = -0.6, panTo = 0.6, shape = 1.6) {
  /* band-limited noise sweep: the swish / whoosh family. f0->f1 = filter centre sweep */
  const i0 = Math.round(t0 * SR), n = Math.round(dur * SR);
  let lp = 0, bp = 0;
  for (let k = 0; k < n; k++) {
    const p = k / n;
    const env = Math.pow(Math.sin(Math.PI * Math.min(1, p * 1.15)), shape);
    const fc = f0 * Math.pow(f1 / f0, Math.sin(Math.PI * p * 0.5));
    const c = Math.min(0.95, 2 * Math.sin(Math.PI * fc / SR));
    const x = noise(); lp += c * (x - lp); bp += c * (lp - bp);
    const s = (lp - bp) * env * g;
    const [pl, pr] = panLR(panFrom + (panTo - panFrom) * p);
    add(sfx, i0 + k, s * pl, s * pr);
  }
}
/* phone speakers cannot play a sub: every hit also gets a 150-400 Hz body and a 2-4 kHz click */
function body(t0, g = 0.4, f = 220, tau = 0.12) {
  const i0 = Math.round(t0 * SR), n = Math.round(tau * 5 * SR);
  for (let k = 0; k < n; k++) { const tt = k / SR; const s = Math.sin(TAU * (f + 120 * Math.exp(-tt / 0.02)) * tt) * Math.exp(-tt / tau) * g; add(sfx, i0 + k, s, s); }
}
function click(t0, g = 0.3) { noisebp(t0, 0.03, 2400, 3800, g * 1.6, 0, 0, 0.5); }
function zap(t0, g = 0.3) {
  noisebp(t0, 0.06, 7000, 9000, g * 1.4, 0, 0, 0.6);
  for (let j = 0; j < 4; j++) tick(t0 + 0.015 + j * 0.012 + rnd() * 0.01, g * 0.35, 5000 + rnd() * 4000);
}
function coin(t0, g = 0.3) {
  [2637, 3520, 4186].forEach((f, j) => blip(t0 + j * 0.012, f, f * 0.995, 0.15, g * (1 - j * 0.25), (rnd() - 0.5) * 0.4));
  noisebp(t0 - 0.05, 0.12, 4000, 6000, g * 0.5);
}
const cues = (score.sfx === false ? [] : info.cues)
  .filter((q) => !COVERED.has(q.type))
  .filter((q) => DENSITY === "rich" || (DENSITY === "standard" ? !SMALL.has(q.type) : BIG.has(q.type)))
  .sort((a, b) => a.t - b.t);
let lastT = -1;
for (const q of cues) {
  const t = q.t;
  if (q.type !== "typing" && t - lastT < 0.08) continue; // never stack two SFX inside 80 ms
  lastT = t;
  switch (q.type) {
    case "swish": noisebp(t - 0.1, 0.16, 2500, 6500, 0.32); break;
    case "riser": { const len = q.len || 0.9; riser(t - len, len, 0.6); break; }   // ENDS on the cue
    case "impact": impact(t, 0.6, sfx, 0.5); body(t, 0.4); click(t, 0.3); break;
    case "boom": impact(t, 0.75, sfx, 1.4); body(t, 0.5, 170, 0.35); click(t, 0.22); break;
    case "thump": { const i0 = Math.round(t * SR); for (let k = 0; k < 0.25 * SR; k++) { const tt = k / SR; const s = Math.sin(TAU * (80 + 40 * Math.exp(-tt / 0.03)) * tt) * Math.exp(-tt / 0.07) * 0.5; add(sfx, i0 + k, s, s); } body(t, 0.3, 240, 0.07); click(t, 0.16); break; }
    case "zap": zap(t); break;
    case "coin": coin(t); break;
    case "flash": noisebp(t - 0.04, 0.3, 6000, 2500, 0.35, 0, 0, 0.8); impact(t, 0.45, sfx, 0.4); break;
    case "paper": noisebp(t - 0.05, 0.25, 1200, 3500, 0.18, -0.3, 0.3, 1.0); break;
    case "ripple": blip(t, 380, 900, 0.12, 0.09); break;
    case "click": tick(t, 0.35, 2400); blip(t, 900, 500, 0.05, 0.12); break;
    case "key": key(t); break;
    case "keycombo": key(t, 0.22); key(t + 0.05, 0.22); break;
    case "typing": { let tt = t; while (tt < t + (q.len || 0.5)) { key(tt, 0.13); tt += 0.055 + rnd() * 0.035; } break; }
    case "enter": tick(t, 0.3, 1200); blip(t, 180, 120, 0.06, 0.2); break;
    case "whoosh": whoosh(t - 0.1, 0.55, 0.35); break;
    case "wipe": whoosh(t, 0.7, 0.55); break;
    case "swoosh": whoosh(t, 0.32, 0.25); break;
    case "hit": impact(t, 0.55); break;
    case "pop": blip(t, 520 + rnd() * 120, 980, 0.07, 0.16, (rnd() - 0.5) * 0.6); break;
    case "tick": tick(t, 0.18, 3600); break;
    case "tok": blip(t, 820, 640, 0.06, 0.18, 0.2, "tri"); break;
    case "swell": riser(t, 0.9, 0.35); break;
    case "scribble": scribble(t, q.len || 0.6, 0.14); break;
    case "write": scribble(t, q.len || 0.6, 0.09); break;
    case "slash": scribble(t, 0.22, 0.22); break;
    case "blips": { const n = Math.max(2, Math.round((q.len || 0.6) / 0.09)); for (let k = 0; k < n; k++) blip(t + k * (q.len || 0.6) / n, mtof(PENTA[Math.floor(rnd() * PENTA.length)]), mtof(PENTA[0]) * 1.5, 0.05, 0.07, (rnd() - 0.5)); break; }
    case "sweep": blip(t, 300, 1400, 0.8, 0.06); break;
    case "riseShort": riser(t, 0.45, 0.35); break;
    case "chime": bell(t, 88, 0.9, -0.2); bell(t + 0.09, 95, 0.7, 0.2); break;
    case "alert": bell(t, 81, 0.7, 0); bell(t + 0.14, 76, 0.6, 0); break;
    default: break;
  }
}

/* ------------------------------------------------------------- reverb (Freeverb) */
function freeverb(inp, room = 0.82, damp = 0.35) {
  const combs = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617];
  const aps = [556, 441, 341, 225];
  const out = [new Float32Array(N), new Float32Array(N)];
  for (let ch = 0; ch < 2; ch++) {
    const spread = ch ? 23 : 0;
    const x = inp[ch];
    const y = out[ch];
    const cb = combs.map((l) => ({ buf: new Float32Array(Math.round((l + spread) * SR / 44100)), i: 0, f: 0 }));
    const ab = aps.map((l) => ({ buf: new Float32Array(Math.round((l + spread) * SR / 44100)), i: 0 }));
    for (let n = 0; n < N; n++) {
      const v = x[n] * 0.015;
      let s = 0;
      for (const c of cb) {
        const o = c.buf[c.i];
        c.f = o * (1 - damp) + c.f * damp;
        c.buf[c.i] = v + c.f * room;
        if (++c.i >= c.buf.length) c.i = 0;
        s += o;
      }
      for (const a of ab) {
        const o = a.buf[a.i];
        a.buf[a.i] = s + o * 0.5;
        if (++a.i >= a.buf.length) a.i = 0;
        s = o - s;
      }
      y[n] = s;
    }
  }
  return out;
}
const rev = freeverb(send);

/* ------------------------------------------------------------- mix */
const L0 = new Float32Array(N), R0 = new Float32Array(N);
for (let i = 0; i < N; i++) {
  const d = duck[i];
  let l = drums[0][i] * 0.82 + bass[0][i] * d * 0.72 + pads[0][i] * (0.55 + 0.45 * d) + keys[0][i] * (0.95 + 0.35 * d) + mfx[0][i] * 0.8 + rev[0][i] * 0.9;
  let r = drums[1][i] * 0.82 + bass[1][i] * d * 0.72 + pads[1][i] * (0.55 + 0.45 * d) + keys[1][i] * (0.95 + 0.35 * d) + mfx[1][i] * 0.8 + rev[1][i] * 0.9;
  // gentle bus saturation
  L0[i] = Math.tanh(l * 0.9) / 0.9;
  R0[i] = Math.tanh(r * 0.9) / 0.9;
}
// fade the very end
const fadeN = Math.round(1.2 * SR);
for (let k = 0; k < fadeN; k++) { const g = 1 - k / fadeN; L0[N - fadeN + k] *= g; R0[N - fadeN + k] *= g; }

/* write 32-bit float WAV */
function wav(file, l, r) {
  const n = l.length, bytes = n * 2 * 4;
  const b = Buffer.alloc(44 + bytes);
  b.write("RIFF", 0); b.writeUInt32LE(36 + bytes, 4); b.write("WAVE", 8);
  b.write("fmt ", 12); b.writeUInt32LE(16, 16); b.writeUInt16LE(3, 20); b.writeUInt16LE(2, 22);
  b.writeUInt32LE(SR, 24); b.writeUInt32LE(SR * 8, 28); b.writeUInt16LE(8, 32); b.writeUInt16LE(32, 34);
  b.write("data", 36); b.writeUInt32LE(bytes, 40);
  for (let i = 0; i < n; i++) { b.writeFloatLE(l[i], 44 + i * 8); b.writeFloatLE(r[i], 48 + i * 8); }
  fs.writeFileSync(file, b);
}
const out = args.out || path.join(project, "build", platform, "music.wav");
fs.mkdirSync(path.dirname(out), { recursive: true });
wav(out, L0, R0);
/* the SFX stem: never ducked, mixed on top by render.py */
const SL = new Float32Array(N), SR_ = new Float32Array(N);
for (let i = 0; i < N; i++) { SL[i] = Math.tanh(sfx[0][i] * 1.1) / 1.1; SR_[i] = Math.tanh(sfx[1][i] * 1.1) / 1.1; }
wav(path.join(path.dirname(out), "sfx.wav"), SL, SR_);
let peak = 0; for (let i = 0; i < N; i++) peak = Math.max(peak, Math.abs(L0[i]), Math.abs(R0[i]));
console.log(JSON.stringify({ sections, palette: PAL, music: out, seconds: +(N / SR).toFixed(2), peak: +peak.toFixed(3), key: score.key, mode: score.mode, progression: score.progression }));
