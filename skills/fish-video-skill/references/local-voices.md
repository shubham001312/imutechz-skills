# Local voices: make them yourself, free, with measured checks

## The recommended default: `chatterbox-soft`

The named preset every recipe, the brief template and the interview use first. Chatterbox's own default voice, one sentence at a time, `exaggeration` 0.32-0.55 by sentence (mood and punctuation move it inside that range), `cfg_weight` 0.25, `temperature` 0.75, `seed` 11 (re-seeded for every sentence), pauses 0.35-0.55 s (under 6 words 0.35, a question 0.5, otherwise 0.45), then `highpass=f=75,equalizer=f=280:t=q:w=1.1:g=-2,equalizer=f=3200:t=q:w=1.4:g=0.8,aexciter=freq=6500:amount=0.5:blend=0:ceil=11500,highshelf=f=8000:g=1.5,deesser=i=0.35,acompressor=threshold=-20dB:ratio=1.8:attack=15:release=180:makeup=1.2,aecho=0.9:0.9:19|37:0.04|0.025` and `loudnorm=I=-18:TP=-2:LRA=9`, 48 kHz. Brief: `voice: {provider: chatterbox, studio: {style: chatterbox-soft}}`, `pacing.max_word_gap: 0.9`, `pacing.line_gap: 0.05`, `mix.music_under_voice_db: -12`.

It reproduces the voice of the long roadmap video (the recipe came from that video's generation script, not from the studio's older `soft` style, which is a different, flatter chain). Measured on the reference machine: the same sentence generated twice from seed 11 is bit-identical; against the long video's first line the pitch was 120 Hz against 118 Hz, level -18.1 against -17.8 dB RMS, equal peaks, and band energies within about 2 dB. Nobody has listened to the comparison: audition it.

Not installed? `fishvideo voice setup --engine chatterbox` (one command, about 2 GB, CPU is enough). Until then `voice`, `audition` and `render` stop and say so. Nothing falls back silently; to use another voice the user picks it (`--provider`, or `voice.studio.style` for another studio style) and you tell them what changes. English only; no voice audio is committed.


Load this when the user wants a free voice made on their own machine, male or female, airy or soft, at a chosen pace, and wants the output tested. Nothing here ships audio or model weights. The tools make the voice on the user's computer.

## What can and cannot be claimed

- **No tool here can hear.** Every check is a measurement: transcript match, pace, pauses, pitch, brightness, level, clipping. None of them can tell whether a voice is "ultra realistic" or "emotional". A person has to listen.
- **Nobody has listened to the samples this skill makes.** The numbers in this file come from automatic measurements of generated audio. Run `voice audition --matrix` and choose by ear before you commit a video to a voice.
- The settings are starting points measured on one CPU-only desktop. Treat them as a recipe to adjust, not as a guarantee.

## Commands

All are `fishvideo voice ...` (or `python scripts/voicelab.py ...`). Engines run in their own environments under `<skill>/.tts/<engine>`, because their pinned dependencies conflict with the skill's own. Override with `FISH_TTS_HOME`, or `FISH_CHATTERBOX_PYTHON` / `FISH_KOKORO_PYTHON` / `FISH_WHISPER_PYTHON` to use an environment you already have.

| Command | What it does |
|---|---|
| `voice setup --engine chatterbox\|kokoro\|all [--dry-run] [--gpu]` | Creates the environment (uv if present, else venv and pip), installs pinned versions with CPU-only torch and `setuptools<81`. Safe to repeat: a finished environment is left alone. Chatterbox is about 6 GB with its model; Kokoro is far smaller. |
| `voice engines` | Which engines are installed and whether transcription works. `fishvideo doctor` lists them too. |
| `voice say "text" --out a.wav --engine E --gender G --style S --pace P` | One line, with the full pipeline and a printed measurement. |
| `voice audition --matrix --out DIR [--pace 2.8 --styles airy,soft --genders male,female]` | One short sample per gender and style, plus `index.md` and `index.json` with measured pace, pauses, pitch, brightness and loudness. Listen to these. |
| `voice check <dir> [--fix]` | Output QA on the narration of a project (below). `--fix` regenerates lines whose words are wrong, with a new seed. |
| `voice redo <dir> <line-id> [--seed N --mood M --style S --exaggeration X --pace P]` | Regenerates one line. The change is saved under `voice.studio.lines.<id>` in the brief, so a later full run keeps it. |
| `voice measure file.wav ...` | Prints the same measurements for any audio file. |

## In a brief

```yaml
voice:
  provider: chatterbox          # or kokoro
  studio:
    gender: female              # male | female
    style: airy                 # airy soft warm calm energetic emotional cinematic
    pace: natural               # slow | natural | fast | a number of words per second, e.g. 2.7
    seed: 11
    aliases: {"q laura": "qlora"}   # words the transcript check may hear differently
```

A scene's `mood:` (neutral, curious, tense, urgent, excited, warm, serious, reflective, triumphant) moves the emotion and the pause of each sentence in it; "!" raises it, "..." lowers it. Presets live in `config/voicelab.yaml`.

## The recipe the studio follows

One sentence at a time (fragments under 3 words join the next sentence). Real pauses of about 0.3-0.6 s between sentences, by style and mood. Chatterbox `cfg_weight` 0.22-0.42 (lower is slower), `exaggeration` 0.34 calm to 0.68 emotional, temperature 0.75, a fixed seed. Air is added afterwards with a gentle ffmpeg chain (`aexciter`, a high shelf, a de-esser, a compressor), then a static gain per line to a common speech level. Chatterbox's watermark stays on; the worker refuses to run if the watermark module failed to import.

**Pace is a closed loop.** After the takes exist, the studio measures words per second over the line (pauses included) and moves, in order: the pause lengths, a time-stretch of at most 6%, and then one regeneration with a changed `cfg_weight` (Chatterbox) or `speed` (Kokoro). The target band is the pace plus or minus 0.15 words per second. Lines under 6 words are not steered.

## Male and female without shipping audio

- **Labels come from measurement.** The median F0 of the voiced frames labels a clip: below 165 Hz reads as male, at or above as female. This is a rule of thumb about pitch, not a statement about a person, and `voice check` warns when the measured label differs from the style you asked for.
- **Kokoro** has preset voices for both (`am_michael`, `bm_george`; `af_heart`, `bf_emma`).
- **Chatterbox** has one built-in voice, which measured as male in these runs. For a female voice the studio makes a reference clip at run time by speaking a short fixed sentence with a Kokoro preset voice, and caches it in the project's build folder. It is never committed.
- **Licence reading for that step.** The Kokoro model card (huggingface.co/hexgrad/Kokoro-82M, `license: apache-2.0`) says: "With Apache-licensed weights, Kokoro can be deployed anywhere from production environments to personal projects", and "This is an Apache-licensed model ... We welcome the deployment of the model in real use cases." It says its training data was "permissive/non-copyrighted audio", with synthetic audio from closed providers listed among the sources. The card puts no restriction on the audio it produces, so using it as a reference for Chatterbox (MIT) is allowed by what the card says. This is a reading of the card, not legal advice: re-read it for your use.
- **Your own clip** goes in `voice.studio.reference` and needs `reference_consent: true` (or `--i-have-consent` on `voice say`): set it only for your own voice or a speaker who agreed. A hosted provider's output (ElevenLabs, edge-tts, Azure, OpenAI, Polly and similar) is refused in code whatever the flag says, because their terms do not allow it as a cloning reference. The code can only catch the skill's own output folders and telling file names; it is a backstop, not proof.

## `voice check` and `fishvideo qa`

Per line: the take is transcribed (faster-whisper) and compared with the script as a word error rate, with digits, punctuation and aliases normalised. A wrong word is regenerated with a new seed up to 2 times during synthesis; a difference that only looks like a respelling ("Lama Index") is flagged, not retried. Then: pace against the target (or a 1.8-4.2 words/s band), pause count against sentence count, clipping, level against the narration's median, head and tail silence, runaway or truncated duration (seconds per word), pitch drift across lines, and the brightness band for the style. `--quality` adds torchaudio's SQUIM estimates (a distortion proxy, not realism).

`fishvideo qa` adds four rows for narration made by the studio (or when `voice.check: true`): `voice words`, `voice pace`, `voice signal`, `voice character`. Without an engine they are skipped, or a WARN says the transcript was not checked. Other providers' QA is unchanged.

## Measured on the reference machine (a CPU-only desktop; nobody has listened)

Line: "A voice is a set of small choices. Slow down, and every word gets room." (14 words). Chatterbox, built-in voice for male, a Kokoro-made reference for female, one seed. Pace is measured on the finished file, pauses included. Pitch is the median F0 of the voiced frames. Brightness is the energy above 6 kHz relative to the whole speech signal. "In band" means within 0.15 words/s of the target.

| gender | style | target | measured | in band | median pitch | reads as |
|---|---|---|---|---|---|---|
| male | airy | 2.4 | 2.54 | yes | 129 Hz | male |
| male | soft | 2.4 | 2.42 | yes | 110 Hz | male |
| male | emotional | 2.4 | 2.73 | no | 132 Hz | male |
| female | airy | 2.4 | 2.53 | yes | 200 Hz | female |
| female | soft | 2.4 | 2.42 | yes | 188 Hz | female |
| female | emotional | 2.4 | 2.64 | no | 216 Hz | female |
| male | airy | 3.2 | 3.24 | yes | 132 Hz | male |
| male | soft | 3.2 | 3.07 | yes | 126 Hz | male |
| male | emotional | 3.2 | 3.23 | yes | 162 Hz | male |
| female | airy | 3.2 | 3.23 | yes | 188 Hz | female |
| female | soft | 3.2 | 3.16 | yes | 195 Hz | female |
| female | emotional | 3.2 | 3.21 | yes | 193 Hz | female |

- 10 of 12 landed in the band. The two misses are the emotional style at the slow target: high `exaggeration` speeds delivery, and the loop ran out of room (the lowest `cfg_weight` it allows, 0.15, the longest pause, a 6% stretch). It reports `converged: false` and `voice check` warns. For a slow emotional read, write shorter sentences or accept a faster pace.
- Brightness measured -16 to -19 dB for Chatterbox and -12 to -16 dB for Kokoro in every style. The "airy" chain moved it by only about 1 to 2 dB against "soft" in Kokoro. So the brightness check is a drift detector, not proof of airiness; only listening can say whether a voice sounds airy.
- Pitch moves with style: Chatterbox's male voice measured 110 Hz soft and 162 Hz emotional, close to the 165 Hz split. A label near the split is weak evidence; say so before relying on it.
- Kokoro (am_michael, af_heart, natural pace, all 7 styles) measured 115 Hz and 201-205 Hz, and its styles differ only by the post chain and pauses, because Kokoro has no emotion control.
- Compute: Chatterbox about 3.6 s per second of speech when the machine is idle; much slower when it is shared.

`voice check` on a project voiced by Kokoro caught a planted fault (a line cut to its first 3 seconds): `FAIL voice words ... heard ''` and `WARN voice pace ... 5.86 wps, target 2.9`. It also FAILed a real mishear, "Tidewell" (respelled "Tide well") heard as "Tied well"; add `studio.aliases: {"tied well": "tide well"}` to accept a transcriber's spelling of a brand word.
