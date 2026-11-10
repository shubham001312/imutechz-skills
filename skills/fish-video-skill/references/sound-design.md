# Sound design and mix

The audio is **three stems**, mixed separately and never on one bus:

| Stem | Source | Processing | Level target |
|---|---|---|---|
| **voice** | TTS clips (ElevenLabs, edge-tts or Kokoro) or the user's own VO | HPF 85 Hz, −2 dB at 280 Hz, +1.5 dB presence at 4.8 kHz, air shelf, comp 2.5:1, short room | about −16 LUFS short-term while speaking |
| **music** (BGM) | a library track (`assets/music/*`, logged in credits) **or** the synthesised score (`music.mjs`) | bass harmonics, gentle −1.5 dB mid dip (`mix.music_carve_db`), mid-band sidechain duck from the voice | `mix.music_under_voice_db` (default **−10 dB** under the voice, measured on a simulated phone) |
| **sfx** | samples from `assets/sfx/`, `sfx/library/` (Kenney CC0, Freesound CC0), else synthesised | none; **not ducked** | per cue type, see the table below |

The sum is loudness-normalised to the platform target (−14 LUFS with true peak −1.5 dBTP on long formats, −12 LUFS with −1 dBTP on Shorts, Reels and TikTok) and limited.

Why it is built this way: in v1 the voice ducked the whole bed, SFX included, at ratio 6 on a −5 dB bed. The BGM vanished under narration and the risers and clicks were swallowed. The references keep music clearly audible, about 8–12 dB under the voice, and keep SFX on top in the word gaps.

## Translating to phone and laptop speakers

Headphones reproduce everything. A phone speaker plays almost nothing below 200–300 Hz, and usually plays mono. A bed of pads and sub bass can sound right on headphones and disappear on a phone. A mix that only works on headphones is a failed mix. The renderer does five things about it:

1. **Levels are balanced through a phone simulation** (`render.PHONE_SIM`: mono, high-pass around 250 Hz, +3 dB at 2.5 kHz, low-pass at 10 kHz). `mix.music_under_voice_db` is measured there, capped by `mix.music_max_fullband_db` so headphones stay balanced.
2. **Psychoacoustic bass.** The low band is saturated, and its 150–1200 Hz harmonics are blended back (`mix.translate`). The ear infers the missing fundamental, so bass stays audible on speakers that cannot play it.
3. **A multiband duck.** Only the mid band (150 Hz–4 kHz, where words live) ducks under the voice. A full-band duck also pulled down the harmonics, which is exactly what a phone relies on.
4. **SFX are calibrated by events, not by integrated loudness**, which hides short sounds. On a phone, a typical SFX event peaks `mix.sfx_under_voice_db` (default −7 dB) below typical speech. Every impact, boom and thump also has a 150–400 Hz body and a 2–4 kHz click, so a phone gets the click and headphones get the body.
5. **Louder masters for vertical platforms:** −12 LUFS with a −1 dBTP ceiling on Shorts, Reels and TikTok.

QA's `speaker translation` check measures how much of the mix a phone throws away, the voice-to-bed gap on a phone, and mono safety. Listen to `build/<platform>/phone-monitor.wav`, or play the final video on a real phone at low volume. A simulation is not a phone.

If the music still vanishes: raise `mix.translate.music_harmonics_db` (−4 → −2), choose a brighter track (a sub-heavy drone has little for a phone to play), or lower `mix.music_under_voice_db` (−10 → −8).

## Cue vocabulary (scene `cues`) and default levels

| cue | sound | length | level (dBFS before master) | place it |
|---|---|---|---|---|
| `swish` | airy noise sweep, 5–6 kHz centroid | 150 ms | −24 | 0.08–0.12 s **before** an element moves |
| `whoosh` | fuller sweep with low body | 350 ms | −20 | on camera moves and zoom-throughs |
| `wipe` | long whoosh | 600 ms | −18 | chapter wipes |
| `riser` (`len`) | noise and tone rising, cut dead | 0.6–1.2 s | −22 → −14 | **ends** on the reveal (`lt` is the end) |
| `impact` / `hit` | sub thump with a short noise burst | 400 ms | −13 | title slams, flash cuts |
| `boom` | deep sub with a long tail | 1.2 s | −15 | big reveals, end card |
| `thump` | 80 Hz, short | 250 ms | −16 | slides, landings |
| `pop` | short tonal blip | 70 ms | −26 | element arrival (rich density) |
| `tick` | 3.6 kHz click | 30 ms | −30 | small labels, counters |
| `click` | mouse click | 40 ms | −20 | every recorded click (screen scenes) |
| `ripple` | soft bubble | 120 ms | −28 | click ripples |
| `zap` | glassy, >5 kHz, crackle tail | 60 ms | −22 | neon vertex hits |
| `coin` | metallic flip | 150 ms | −22 | coin flips |
| `paper` | paper slide or rustle | 250 ms | −24 | collage cards entering |
| `flash` | air burst with impact | 300 ms | −16 | white flash transitions |
| `typing` (`len`) | key run | len | −26 | terminal and screen typing |
| `scribble` (`len`) | marker | len | −24 | whiteboard strokes |
| `chime`, `swell`, `blips`, `sweep`, `key`, `keycombo`, `enter`, `tok`, `alert` | v1 synth cues, kept | | | |

### Your own cue types

Add a folder `assets/sfx/<type>/` and use `<type>` as a cue. Its level comes from `brief.mix.sfx_levels: {<type>: -14}`, or -22 dBFS by default.

### Density (`sfx.density` from the interview)

- **rich**: every cue is placed. Use it for Shorts and motivational or explainer pieces.
- **standard**: transitions, reveals, impacts, risers and clicks only. Pops and ticks are dropped.
- **minimal**: impacts, risers and booms only (as in R5, stick-figure or music-led pieces).

Two rules apply at every density:
- Never stack more than 2 SFX within 80 ms. The later one is dropped.
- No `pop` or `tick` is placed within 60 ms of a stressed spoken word.

## Music

There are two sources, chosen in the interview (`music.mood`, `music.source`).

1. **A library track** (preferred when real assets are allowed).
   - `fishvideo assets search <dir> --kind music --q "<mood words>"`.
   - Or the user drops a file in `assets/music/`.
   - The renderer finds its tempo, trims it to length on a bar line, fades the last 1.5 s, and logs it in `credits.json`.
   - Licences allowed: CC0, Pixabay Content License, CC-BY (credited). Never NC or ND, and never anything ripped from YouTube.
2. **Synthesised score** (`music.mjs`).
   - Moods map to key/mode/progression/tempo presets in `config/styles.yaml`.

Bed rules:
- The music starts at frame 0 (no fade-in on Shorts).
- It is audible in every gap.
- It is ducked about 6 dB under the voice (attack 10 ms, release 250 ms).
- It fades over the last 1.5 s, or cuts dead after a final impact when the style says `end: silence`.

## Mix settings (`config/defaults.yaml` → `mix:`)

```yaml
mix:
  voice_lufs: -16            # voice stem normalised to this before summing
  music_under_voice_db: -10  # music under the voice, on a simulated phone
  music_max_fullband_db: -6  # never louder than this under the voice, full range
  music_carve_db: -1.5       # gentle static mid dip
  translate: {music_drive_db: 14, music_harmonics_db: -4, music_width: 0.85, sfx_drive_db: 16, sfx_harmonics_db: -6}
  duck: {threshold: 0.05, ratio: 3, attack: 10, release: 250, makeup: 1}   # mid band only
  sfx_gain_db: 0             # manual trim on the SFX stems
  sfx_under_voice_db: -7     # automatic: a typical SFX event on a phone, relative to speech
  sfx_max_boost_db: 12
```

QA measures the stems: the voice-to-music gap while speaking should be between 6 and 14 dB, music in the gaps must be no quieter than −30 LUFS short-term, and SFX must be audible (at least 3 events above −35 dBFS for rich density). A WARN tells you which knob to turn.

QA also checks every placed SFX cue one by one (`sfx audibility`): in the window from 0.1 s before to 0.5 s after the cue it compares the SFX stems (with the gain the mix applied, recorded in `build/<platform>/mix.json`) with the voice stem. A cue that is silent there, or more than 18 dB under the voice while someone is speaking, is a WARN naming its time: raise `mix.sfx_gain_db` or `mix.sfx_under_voice_db`, or check that the cue type has a sound.

## Listening check (do it yourself)

Use `dissect.py` on your own `final.mp4` and compare its `timeline.md` balance numbers with a reference's. Then open `spectrogram.png`. You should see:
- the voice harmonics on top
- a steady music layer underneath that never disappears
- thin swish smears just before each cut
