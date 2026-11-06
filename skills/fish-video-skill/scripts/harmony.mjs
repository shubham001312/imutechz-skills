/* Harmony helpers for music.mjs (pure; unit-tested). */
/* diatonic harmony from key + mode + a roman-numeral progression */
export const NOTE = { C: 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, F: 5, "F#": 6, Gb: 6, G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11 };
export const SCALES = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10], dorian: [0, 2, 3, 5, 7, 9, 10], mixolydian: [0, 2, 4, 5, 7, 9, 10], phrygian: [0, 1, 3, 5, 7, 8, 10], lydian: [0, 2, 4, 6, 7, 9, 11] };
const ROMAN = { i: 0, ii: 1, iii: 2, iv: 3, v: 4, vi: 5, vii: 6 };
export function buildProgression(key, mode, prog) {
  const sc = SCALES[mode] || SCALES.minor;
  const k = NOTE[key] != null ? NOTE[key] : 2;
  const deg = (d) => sc[((d % 7) + 7) % 7] + 12 * Math.floor(d / 7);
  return String(prog).split(/[-\s]+/).filter(Boolean).map((r) => {
    const d = ROMAN[r.toLowerCase().replace(/[^iv]/g, "")];
    if (d == null) throw new Error(`bad chord numeral "${r}" in progression "${prog}"`);
    let root = 36 + k + deg(d); if (root > 43) root -= 12;
    const base = 48 + k + deg(d); const shift = base > 57 ? -12 : 0;
    const notes = [0, 2, 4, 6, 8].map((o) => 48 + k + deg(d + o) + shift);
    return { root, notes };
  });
}

/* Sections: the arrangement follows scene energy. A new section starts where the energy changes, and a long run of one
   energy is split every `maxRun` bars so a long video never loops one texture. Returns sec[bar] = section index. */
export function planSections(energy, bars, maxRun = 8) {
  const sec = new Array(bars).fill(0);
  let idx = 0, run = 0;
  for (let b = 0; b < bars; b++) {
    if (b > 0 && (energy[b] !== energy[b - 1] || run >= maxRun)) { idx++; run = 0; }
    sec[b] = idx; run++;
  }
  return sec;
}
const ARPS = [[0, 2, 4, 1, 3, 2, 4, 3], [0, 1, 2, 3, 4, 3, 2, 1], [0, 4, 2, 3, 1, 4, 2, 0], [0, 2, 0, 3, 0, 4, 0, 3]];
const BASS = [[1, 0, 1, 1, 0, 1, 1, 0], [1, 0, 0, 1, 0, 0, 1, 0], [1, 1, 0, 1, 1, 0, 1, 0], [1, 0, 1, 0, 1, 0, 0, 1]];
/* What section `i` plays: lead voice, arpeggio shape, bass rhythm, chord rotation. Neighbouring sections always differ. */
export function sectionSig(i, pal = {}) {
  const leads = pal.leads && pal.leads.length ? pal.leads : ["pluck"];
  return { lead: leads[i % leads.length], arp: (((pal.arp | 0) + i) % ARPS.length), bass: (((pal.bass | 0) + i) % BASS.length), rot: i % 3 === 2 ? 1 : 0 };
}
export const arpPattern = (n) => ARPS[n % ARPS.length];
export const bassPattern = (n) => BASS[n % BASS.length];
export const sigKey = (s) => `${s.lead}/${s.arp}/${s.bass}/${s.rot}`;
