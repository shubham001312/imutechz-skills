# Voice direction

## The default voice

| | |
|---|---|
| Provider | **ElevenLabs** (default) |
| Voice | `fydPJq00SigRIaPxWgiS`, English (India): https://elevenlabs.io/voices/fydPJq00SigRIaPxWgiS |
| Model | `eleven_multilingual_v2` |
| Settings | stability 0.42 · similarity_boost 0.8 · style 0.18 · use_speaker_boost true · speed 0.96 (max 1.12) |
| Context | `previous_text` / `next_text` sent with every line (`use_context: true`), so the intonation carries across lines |
| Endpoint | `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128`, header `xi-api-key` |
| Key | `ELEVENLABS_API_KEY` from the environment, or from a **gitignored** `.env` in the project or skill folder. Never printed, logged, written to metadata, or committed. |
| Fallback | **edge-tts** `en-IN-NeerjaNeural`, rate -6%, pitch +0 Hz. It is free and needs internet. It is used automatically when no key is set, or when an ElevenLabs call fails; the run prints a `!!` line saying so, and `metadata.json` records `stand_in_for`. |

These settings match `Promotion/src/explainer/voice.config.json`, which is used for the ImuTechz explainer. Change them per project in `brief.yaml` under `voice:`.

```yaml
voice:
  provider: elevenlabs          # elevenlabs | edge-tts | none
  language: en-IN
  elevenlabs: {voice_id: fydPJq00SigRIaPxWgiS, model_id: eleven_multilingual_v2,
               voice_settings: {stability: 0.42, similarity_boost: 0.8, style: 0.18, use_speaker_boost: true, speed: 0.96}}
  fallback: {provider: edge-tts, voice: en-IN-NeerjaNeural, rate: "-6%"}
  pronunciations: {IMURUN: "Imu run", GGUF: "G G U F", ImuTechz: "Imu techs"}
```

## Word timings

- **ElevenLabs** returns `alignment.characters` with start and end times per character. `voice.eleven_words` groups characters into words on whitespace. A word is timed by its *letters and digits only*, so a trailing comma does not stretch the word.
- **edge-tts** emits `WordBoundary` events (offset and duration in 100 ns ticks). The script locates each one in the spoken string to get a character index.
- Both are mapped back to **displayed** words through the `{shown|spoken}` units. Captions therefore show "GGUF" while the voice says "G G U F".

## Respelling: `{shown|spoken}`

Write what the viewer should *read* on the left and what the voice should *say* on the right.

| Shown | Spoken | Why |
|---|---|---|
| `{GGUF\|G G U F}` | letters | Acronyms spelled out |
| `{SQL\|sequel}` | a word | Acronyms said as words, where that is the convention |
| `{v0.3\|version zero point three}` | expanded | Versions |
| `{10,631\|ten thousand six hundred and thirty-one}` | words | Big numbers (en-IN may otherwise say "ten thousand, six thirty-one") |
| `{2.1×\|two point one times}` | words | Symbols |
| `{C++\|C plus plus}` | words | Punctuation in names |
| `{Ctrl K\|Control K}` | full | Keys |
| `{imutechz.in\|Imu techs dot in}` | spoken URL | Domains |
| `{Qwen\|Kwen}`, `{Phi\|Fye}`, `{LoRA\|Lora}` | phonetic | Brand and model names |
| `{R&D\|R and D}` | words | Ampersands |
| `{₹499\|four hundred and ninety-nine rupees}` | words | Currency, in the locale's order |

Put recurring words in `voice.pronunciations` once. They are applied to every line as whole words, but never inside an existing pair.

## Directing the read

- **Write for the ear.** Use short sentences, and put the verb early. Give one idea per line, because each line is one TTS call, one clip and one caption group.
- **Punctuation is direction.**
  - A comma is a short breath.
  - An ellipsis `…` is a held, thinking pause; use it before a reveal.
  - A colon sets up a list or payoff.
  - An em dash is an aside.
  - Question marks lift the pitch, so avoid them unless you mean them.
- **Emphasis:** the TTS stresses the new information at the end of a sentence. Put the key word last: "…runs on *your machine*."
- **Numbers:** say them once, clearly. Don't stack two numbers in one sentence.
- **Pace:** ElevenLabs speed 0.92–1.0 for explainers, 1.0–1.08 for promos. edge-tts rate -8% to +4%.
  - If a scene has a fixed `bars` and the line overruns, cut words before you speed up.
  - Never exceed `max_speed` 1.12 or `max_rate` +8%.
- **Consistency:** keep one voice per video, and keep settings identical across lines. Changing the text of one line re-voices only that line, because clips are cached by text and settings.

## Chatterbox: a free local voice with emotion control

**Recommended default: the `chatterbox-soft` preset** (recipe and measurements in [local voices](local-voices.md)). The settings below are the recipe it implements.

Use it when the user wants a natural voice with no paid plan and no GPU. In one audition, a user chose this route over the free edge voices; that is one listener and not a blind test, so always audition.

**Setup, in its own environment.** Its pinned dependencies conflict with the skill's venv:

```bash
uv venv --python 3.11 .tts/chat
uv pip install --python .tts/chat/bin/python chatterbox-tts "setuptools<81"
```

Without `setuptools<81` it fails with `TypeError: 'NoneType' object is not callable`: the watermark module needs `pkg_resources`, and its failed import is swallowed. Keep the watermark on.

**Its default pace is too fast and has almost no pauses:** about 4 words/s on a 40-word paragraph. Measured on a CPU-only Ryzen 7 8700G:

- Generate **one sentence at a time** and join them with silences of 0.35-0.55 s. Merge fragments under 3 words into the next sentence.
- `cfg_weight` 0.25-0.3 slows the delivery. Together with the silences this gave about 2.9 words/s.
- Set `exaggeration` per sentence: 0.32 calm, 0.42 warm, 0.55 animated. Put more emotion in the words too: "..." and "!" change the delivery.
- Use `temperature` 0.75 and a fixed seed.
- Speed: about 3.6 s of compute per second of speech.
- Respell acronyms for the model ("Q Laura" for QLoRA, "face" for FAISS) and keep the normal spelling in the storyboard.

**Check every sentence.** Takes can drop or change words, and a listener may not catch it. Transcribe each take, compare it with the script, and regenerate with a new seed when they disagree.

**Airiness:** add it after generation with a gentle chain, and measure. High-frequency energy relative to the overall level is easy to overshoot, which sounds hissy: `aexciter=freq=6500:amount=0.5:blend=0:ceil=11500,highshelf=f=8000:g=1.5,deesser=i=0.35`.

**Bring it in** as a recording: `fishvideo voiceover <dir> narration.wav`. This route applies no second post chain. Raise `pacing.max_word_gap` (for example to 0.9), or the import cuts the pauses you just made. If the skill's venv cannot install `faster-whisper`, transcribe in another environment and save the word list as JSON (`[{"text","start","end"}]`, seconds) and run `fishvideo voiceover <dir> narration.wav --words words.json`.

**Reference clips.** Never use a hosted provider's output (ElevenLabs, edge-tts, Azure, OpenAI, Polly and similar) as a reference clip: their terms do not grant that use, and `voicelab.check_reference` refuses the skill's own output folders and telling file names (a backstop, not proof). A clip you recorded yourself needs `voice.studio.reference_consent: true`. For a gender Chatterbox's built-in voice lacks, the studio makes the reference at run time from a Kokoro preset voice; see [local voices](local-voices.md) for the licence reading.

### Open-source TTS compared (November 2026; this changes quickly)

| Model | Licence | CPU only? | Notes |
|---|---|---|---|
| Chatterbox | MIT, watermarked | Yes, about 3.6x real time here | Emotion control, voice cloning from a short clip |
| Kokoro | Apache-2.0 | Yes, about 0.35x real time here | Fast; preset voices |
| Orpheus | Apache-2.0 | Reported to need about 8-12 GB | Not tested here |
| Higgs Audio v2 | Check the licence per release | Reported GPU-heavy | Not tested here |
| Fish Audio Drama 3 | Community licence with a revenue cap | No | Reported to need about 32-48 GB of NVIDIA memory |
| VibeVoice | Weights reported research only | Slow | Not for commercial use |

For the closest match to a human in blind tests, check the [Artificial Analysis leaderboard](https://artificialanalysis.ai/text-to-speech/leaderboard): at this date the top entries were paid models. Licences above come from secondary sources unless a model card was read, so confirm them before commercial use.

## Locales

| Locale | ElevenLabs | edge-tts fallback voices | Notes |
|---|---|---|---|
| en-IN (default) | `fydPJq00SigRIaPxWgiS` | `en-IN-NeerjaNeural` (f), `en-IN-PrabhatNeural` (m) | about 145 wpm; Indian number words ("lakh", "crore") only if the brand uses them |
| hi-IN | any multilingual_v2 voice with `language_code: hi` | `hi-IN-SwaraNeural` (f), `hi-IN-MadhurNeural` (m) | about 130 wpm; captions in Devanagari (Noto Sans Devanagari is bundled); keep product names in Latin script |
| en-US | multilingual voices | `en-US-AriaNeural`, `en-US-AndrewMultilingualNeural`, `en-US-GuyNeural` | about 155 wpm |
| en-GB | | `en-GB-SoniaNeural`, `en-GB-RyanNeural` | about 150 wpm |
| ta-IN, bn-IN, mr-IN, te-IN | multilingual_v2 | `ta-IN-PallaviNeural`, `bn-IN-TanishaaNeural`, `mr-IN-AarohiNeural`, `te-IN-ShrutiNeural` | check whether the caption font covers the script; add a Noto face via `brand.font_files` |
| es, fr, de | multilingual_v2 | `es-ES-ElviraNeural`, `fr-FR-DeniseNeural`, `de-DE-KatjaNeural` | text expands 15–30%; recheck the fits |

List voices with `python scripts/voice.py voices --locale en-IN`. The command lists edge-tts voices, plus your ElevenLabs voices when a key is set.

## No narration

Set `voice: {provider: none}` for a music-only cut. Scenes then size from their animation, captions are empty, and on-screen text has to carry the message. Use kinetic and bullets more, and add 1–2 bars to every text scene.

## Checklist

- [ ] Every acronym, number, symbol and brand word is respelled.
- [ ] I listened to the first and last line and to every number.
- [ ] No line is longer than about 20 words.
- [ ] The run says which provider was used. If it was the fallback, the user knows.
