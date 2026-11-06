# Pacing and music: editing on a 120 BPM bar grid

## The grid

- At 120 BPM, one **beat** is 0.5 s and one **bar** (4 beats) is **2.0 s**. At 30 fps that is 15 frames a beat and 60 frames a bar.
- **Default (`pacing.snap: speech`): the narration drives time.** A narrated scene lasts lead-in + lines + gaps + tail exactly (gaps 0.15-0.35 s, a line's `pause:` up to 0.8 s); the music sections move to the nearest bar. The bar rules below apply only with `snap: bar` (opt-in) and to silent scenes.
- **In bar mode every scene is a whole number of bars**, so every cut lands on a downbeat.
- Inside a scene, **entrances land on beats**: title words at beat 1, the subtitle at beat 3, chips every half beat from beat 5.
- `storyboard.py` sizes scenes in bars:

```
need  = max(min_visual(scene), lead_in + Σ(narration lines + gaps) + tail)
bars  = ceil(need / 2.0)
```

The defaults are `lead_in` 0.35 s, `line_gap` 0.30 s and `tail` 0.55 s. The first word arrives just after the cut, and the picture holds a breath after the last word.

Why this works:
- The music synthesiser builds its arrangement bar by bar, so a scene change *is* a musical phrase change.
- Risers end exactly on the cut, and impacts hit on it.
- The viewer feels the edit as intentional even when nobody notices the grid.

## Pacing rules of thumb

| Scene | Bars | Notes |
|---|---|---|
| hook | 1.5–3 | Under 3 s to the first payoff. No logo first. |
| title | 2–4 | Logo → name → promise → chips, on beats. |
| kinetic | 1–3 | About 6 words a line; hold ≥ 1 s after the last word. |
| bullets / steps | 2–4 | One item per narration beat; ≥ 1 s per item. |
| whiteboard | 3–6 | Draw while speaking. The takeaway arrives last and holds ≥ 1.5 s. |
| stat | 2 | Count up over 2 beats, then hold. |
| tour | 2–6 | One callout at a time, ≥ 2 s each. Speed 1.0–1.6×. |
| end | 2–3 | Energy 0, hold ≥ 2 s on the final frame. |

Further rules:
- **Never hold a frame without motion for more than about 4 s.** If the narration is long, add drawing, a camera move or a callout.
- **Reading time for on-screen text:** at least `0.3 s + 0.06 s × characters`, at the latest after the element has fully arrived.
- **Narration rate:** en-IN about 145 wpm (edge-tts Neerja at -6%; ElevenLabs at speed 0.96). Budget about 2.4 words per second of *scene*, which leaves the music room.
- **Cut length variety:** alternate long and short scenes (3, 2, 4, 2…). Five equal scenes in a row feel mechanical.
- **Chapter wipes:** use them every 20–40 s in long cuts. The wipe straddles the cut (±0.34 s) and carries a whoosh.
- **Reference matching:** `reference.py` reports the median shot length in bars. If the reference cuts every 1.5 bars and yours every 3, your video will feel slower than the reference. Either split scenes or speed the inner animation.

## Energy curve

Each scene has an `energy` from 0 to 3, which the music follows:

| energy | arrangement |
|---|---|
| 0 | pads, sparse plucks, a bell figure at the outro |
| 1 | kick on 1 and 3, off-beat hats, long bass notes, 8th-note plucks |
| 2 | four-on-the-floor kick, clap on 2 and 4, 16th plucks, syncopated bass |
| 3 | + shaker 16ths, open hat, bell motif every other bar |

Transitions follow these rules:
- **Before a lift** (when the next bar's energy is higher), a 0.75-bar riser plays, with a clap roll in the second half.
- **On the lift**, an impact lands.
- **Into energy 0 at the end**, an impact plays, followed by a falling bell figure.

Defaults by scene:
- The first scene is 1, and `end` is 0.
- `tour` and `stat` are 3.
- Most others are 2. `quote` and `image` are 1.

A good curve for a 60 s explainer: `1 → 2 → 2 → 2 → 3 (proof) → 2 → 0`. Lift into the proof and the tour, and land on 0 for the end card.

## The score (music.mjs)

The score is fully synthesised in JavaScript, 48 kHz stereo float, and seeded so a re-render is identical. That means no samples, no stems and no licences. Settings live in `score:` in the brief or storyboard:

```yaml
score: {key: D, mode: minor, progression: i-VI-III-VII, seed: 12345, drums: true, sfx: true}
```

| progression | mood |
|---|---|
| `i-VI-III-VII` (minor, default) | driving, hopeful-serious, the "tech explainer" sound |
| `i-iv-VI-V` (minor) | tense, building |
| `I-V-vi-IV` (major) | bright, upbeat promo |
| `vi-IV-I-V` (major) | warm, emotional |
| `I-vi-IV-V` (major) | classic, friendly |

Chords are diatonic 9th voicings (root, 3rd, 5th, 7th, 9th). Bass is the root at octave 2.

The layers are:
- kick (sine sweep 156→46 Hz, with a sidechain duck on everything tonal)
- clap (three noise bursts through a band-pass)
- hats and a shaker
- sub bass (sine + 2nd + 3rd harmonics, filtered)
- pads (3 detuned saws per note, a two-pole low-pass with an LFO)
- a pluck arpeggio with a dotted-eighth ping-pong delay
- an FM bell
- risers and impacts
- a Freeverb room on a send bus
- tanh bus saturation and a 1.2 s fade at the end

## Sound design cues

Scenes export cues (`cues(c) → [{lt, type, len}]`), and the mixer places them:

| cue | sound | use for |
|---|---|---|
| `hit` | low impact | a title landing, a big reveal |
| `swell` / `rise` / `riseShort` | riser | before a reveal |
| `whoosh` / `swoosh` / `wipe` | filtered noise sweep (panned) | movement, a window entering, chapter wipes |
| `pop` | short pitched blip | a chip, card or callout appearing |
| `tick` | click | a small text entrance |
| `click` | UI click | recorded clicks (automatic from captures) |
| `key` / `keycombo` / `typing` / `enter` | keyboard | recorded keys, terminal typing |
| `scribble` / `write` / `slash` | marker on a board | whiteboard strokes, handwriting, strike-through |
| `blips` | pentatonic blips in the key | counters, cells lighting up |
| `sweep` | rising tone | chart bars growing |
| `chime` / `alert` | bells | success, approval card |

Rule: **every visible event gets a sound, and no sound plays without a visible event.** At most one prominent SFX per beat.

## Mixing with a voice

- The music bed sits 10 dB under the voice (`mix.music_under_voice_db`), carved and ducked about 6 dB while speaking; SFX are a separate, unducked stem. See [sound design](sound-design.md).
- `sidechaincompress` keyed by the voice ducks the bed further while the voice speaks: threshold 0.04, ratio 6, attack 20 ms, release 380 ms.
- The voice post chain: high-pass at 85 Hz, -2 dB at 280 Hz, +1.5 dB at 4.8 kHz, +3 dB shelf at 9 kHz, gentle 2.5:1 compression, a short 23/41 ms room.
- The master gets two-pass `loudnorm` to I = -14 LUFS, TP = -1.5 dBTP, LRA = 11, linear mode, measured first.
