/* Node unit tests: node --test tests/ */
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildProgression, planSections, sectionSig, sigKey } from "../scripts/harmony.mjs";
import { autoActions, runAction } from "../scripts/capture.mjs";
import { parseArgs } from "../scripts/common.mjs";
import fs from "node:fs";
import vm from "node:vm";

test("D minor i-VI-III-VII matches the ImuTechz score voicings", () => {
  const p = buildProgression("D", "minor", "i-VI-III-VII");
  assert.deepEqual(p.map((c) => c.root), [38, 34, 41, 36]);
  assert.deepEqual(p[0].notes, [50, 53, 57, 60, 64]); // Dm9
});

test("major progressions and bad numerals", () => {
  const p = buildProgression("C", "major", "I-V-vi-IV");
  assert.equal(p.length, 4);
  assert.deepEqual(p[0].notes.slice(0, 3), [48, 52, 55]); // C E G
  assert.throws(() => buildProgression("C", "major", "I-X"));
});

test("auto tour fills the requested length with marks", () => {
  const acts = autoActions({ seconds: 10 }, { w: 1440, h: 810 }, 30);
  let frames = 0;
  for (const a of acts) frames += a.hold || a.frames || 0;
  assert.ok(Math.abs(frames - 300) <= 3, `frames ${frames}`);
  assert.ok(acts.some((a) => a.mark === "s1"));
});

test("runAction dispatches to the shot", async () => {
  const calls = [];
  const s = {
    fps: 30, id: "t",
    hold: async (n) => calls.push(["hold", n]), mark: (m) => calls.push(["mark", m]),
    moveTo: async (x, y, n) => calls.push(["move", x, y, n]), click: async (n) => calls.push(["click", n]),
    type: async (t) => calls.push(["type", t]), key: async (k) => calls.push(["key", k]),
    scrollTo: async (y, n) => calls.push(["scroll", y, n]), eval: async () => 100,
    locate: async () => ({ x: 10, y: 20, top: 500 }),
  };
  await runAction(s, { wait: 1 });
  await runAction(s, { mark: "a" });
  await runAction(s, { move: { text: "Pricing" }, s: 0.5 });
  await runAction(s, { scroll: { text: "Features" }, offset: 100 });
  await runAction(s, { scroll: { by: 50 }, frames: 10 });
  assert.deepEqual(calls, [["hold", 30], ["mark", "a"], ["move", 10, 20, 15], ["scroll", 400, 36], ["scroll", 150, 10]]);
  await assert.rejects(() => runAction(s, { nope: 1 }));
});

test("parseArgs", () => {
  assert.deepEqual(parseArgs(["p", "--platform", "yt", "--lint", "--at", "1,2"]), { _: ["p"], platform: "yt", lint: true, at: "1,2" });
});

/* ---- stage maths: lib.js runs in a bare context (it touches the DOM only when called) ---- */
function stageLib() {
  const window = {};
  const ctx = vm.createContext({ window, console, Math, URLSearchParams });
  vm.runInContext(fs.readFileSync(new URL("../scripts/stage/lib.js", import.meta.url), "utf8"), ctx);
  return window.L;
}

test("L.spring: analytic damped spring", () => {
  const L = stageLib();
  const cfg = { stiffness: 100, mass: 1, damping: 10 }; // w0 = 10, zeta = 0.5
  assert.equal(L.spring(0, cfg), 0);
  assert.equal(L.spring(-1, cfg), 0);
  const w1 = 10 * Math.sqrt(1 - 0.25), t = 0.2;
  const want = 1 - Math.exp(-5 * t) * (Math.cos(w1 * t) + (5 / w1) * Math.sin(w1 * t));
  assert.ok(Math.abs(L.spring(t, cfg) - want) < 1e-12);
  assert.ok(Math.abs(L.spring(3, cfg) - 1) < 1e-3, "settles at 1");
  // zeta 0.5 overshoots; the premium preset (zeta 0.7-0.85) barely does; critically and over damped never do
  const peak = (o) => { let m = 0; for (let x = 0; x < 3; x += 1 / 240) m = Math.max(m, L.spring(x, o)); return m; };
  assert.ok(peak(cfg) > 1.1);
  const z = L.SPRING.premium.damping / (2 * Math.sqrt(L.SPRING.premium.stiffness * L.SPRING.premium.mass));
  assert.ok(z >= 0.7 && z <= 0.85, `premium zeta ${z}`);
  assert.ok(peak(L.SPRING.premium) < 1.05);
  for (const damping of [20, 40]) { assert.ok(peak({ stiffness: 100, mass: 1, damping }) <= 1 + 1e-9); assert.ok(L.spring(4, { stiffness: 100, mass: 1, damping }) > 0.9); }
  assert.equal(L.spring(0.37, cfg), L.spring(0.37, cfg), "pure");
});

test("L.placeLabel: stays in bounds and moves off objects and other labels", () => {
  const L = stageLib();
  const bounds = { x0: 64, y0: 240, x1: 940, y1: 1300 };
  const disc = (x, y) => Math.hypot(x - 500, y - 700) < 300;
  const a = L.placeLabel({ w: 240, h: 80, want: { x: 400, y: 660 }, bounds, hit: disc, pad: 10 });
  assert.ok(a.free && a.moved);
  assert.ok(a.x >= 64 && a.x + 240 <= 940 && a.y >= 240 && a.y + 80 <= 1300);
  for (const [x, y] of [[a.x, a.y], [a.x + 240, a.y], [a.x, a.y + 80], [a.x + 240, a.y + 80], [a.x + 120, a.y + 40]]) assert.ok(!disc(x, y));
  const b = L.placeLabel({ w: 240, h: 80, want: { x: a.x, y: a.y }, bounds, hit: disc, rects: [{ x: a.x, y: a.y, w: 240, h: 80 }], pad: 10 });
  assert.ok(b.free && (b.x + 240 <= a.x || b.x >= a.x + 240 || b.y + 80 <= a.y || b.y >= a.y + 80), "labels do not overlap");
  const c = L.placeLabel({ w: 240, h: 80, want: { x: 100, y: 300 }, bounds, hit: disc, pad: 10 });
  assert.deepEqual([c.x, c.y, c.moved], [100, 300, false]);
  assert.deepEqual(a, L.placeLabel({ w: 240, h: 80, want: { x: 400, y: 660 }, bounds, hit: disc, pad: 10 }), "deterministic");
  // nowhere to go: reported, so the caller can make room
  assert.equal(L.placeLabel({ w: 240, h: 80, want: { x: 100, y: 300 }, bounds, hit: () => true }).free, false);
});

test("L.capGroups: by delivery, sentence ends and gaps; covers every word in order", () => {
  const L = stageLib();
  const said = (txt, gaps = {}) => { let t = 0; return txt.split(" ").map((w, i) => { t += gaps[i] || 0; const o = { w, t0: t, t1: t + 0.2 }; t += 0.2; return o; }); };
  const ws = said("one two three four five six seven eight nine ten. eleven twelve thirteen", { 6: 0.2 });
  for (const [delivery, limit] of [["punchy", 3], ["conversational", 5], ["calm", 6]]) {
    assert.equal(L.capLimit(delivery), limit);
    const g = L.capGroups(ws, delivery);
    assert.deepEqual([...g.flatMap((q) => [...q.ws.map((w) => w.w)])], ws.map((w) => w.w), "by position, none lost");
    assert.ok(g.every((q) => q.ws.length <= limit));
    g.forEach((q, i) => {
      assert.ok(q.start <= q.ws[0].t0 && q.end >= q.ws[q.ws.length - 1].t1, "open at or before the first word, close at or after the last");
      if (g[i + 1]) assert.ok(q.end <= g[i + 1].start + 1e-9, "never into the next group");
    });
    assert.ok(g.some((q) => q.ws[q.ws.length - 1].w === "ten."), "breaks at a sentence end");
    assert.ok(g.some((q) => q.ws[0].w === "seven"), "breaks at a 150 ms gap");
  }
  const weak = L.capGroups(said("they kept going the longest"), "punchy");
  assert.equal(weak[0].ws.map((w) => w.w).join(" "), "they kept going");
  assert.equal(L.capGroups(said("we kept the rewards coming"), "punchy")[0].ws.map((w) => w.w).join(" "), "we kept", "a weak word opens the next group");
});

test("L.capGroups: a pause never leaves a lone connecting word as a caption", () => {
  const ctx = { window: {}, document: { documentElement: { style: { setProperty() {} }, classList: { add() {} } } } };
  vm.createContext(ctx); vm.runInContext(fs.readFileSync(new URL("../scripts/stage/lib.js", import.meta.url), "utf8"), ctx);
  const L = ctx.window.L;
  const words = "The army sent two Lewis guns and 10,000 rounds.".split(" ").map((w, i) => ({ w, t0: i * 0.3 + (i >= 6 ? 0.9 : 0), t1: i * 0.3 + 0.25 + (i >= 6 ? 0.9 : 0) }));
  const texts = L.capGroups(words, "calm").map((g) => g.ws.map((w) => w.w).join(" "));
  assert.ok(!texts.includes("and"), texts.join(" | "));
  assert.ok(texts.every((t) => t.split(" ").length > 1), texts.join(" | "));
});

test("a long video has at least 3 distinct music sections and neighbours differ", () => {
  const energy = [1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 2, 2, 2, 2, 1, 1, 1, 0];
  const sec = planSections(energy, energy.length, 8);
  const sigs = [...new Set(sec)].map((i) => sigKey(sectionSig(i, { leads: ["pluck", "bell"], arp: 1, bass: 2 })));
  assert.ok(new Set(sigs).size >= 3, sigs.join(","));
  for (let i = 1; i < sigs.length; i++) assert.notEqual(sigs[i], sigs[i - 1]);
});
