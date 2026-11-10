# Open-source field guide

This is what the best open-source projects in each field do, and what this skill took from them. We **reimplement ideas in our own code**. Nothing here is copied, and GPL/AGPL/non-commercial projects supplied ideas only.

Tags: **[read]** = verified in the project's files or GitHub metadata on 2026-11-04. **[memory]** = from general knowledge and not re-verified; check it before relying on it, especially licences. Stars change, so don't choose by them alone.

## What we adopted

| Field | Best project | Licence | What we took | Where |
|---|---|---|---|---|
| Agent-driven HTML video | heygen-com/hyperframes (78.8k★) | Apache-2.0 [read] | Motion numbers, easing by role, caption grouping, the review loop | `references/scene-catalogue.md` Motion rules, `scripts/review.py` |
| Springs | remotion (custom licence, ideas only), revideo (MIT) | [read] | An analytic damped spring, deterministic at any fps | `L.spring` |
| Silence cutting | auto-editor (5.8k★) | Unlicense [read] | Cut by real audio level, not word timings; speed up idle stretches | `voice.tighten`, `screenrec tighten` |
| Scene detection | PySceneDetect (5.4k★) | BSD-3 [read] | AdaptiveDetector ratio: change ÷ neighbours' change ≥ 3, change ≥ a floor, minimum gap (no false cuts on pans) | `dissect.py` |
| Word alignment | WhisperX (25k★, BSD-2), faster-whisper | [read] | Align a user's voiceover to the script | `voiceover.py` |
| Music analysis | librosa (8.8k★) | ISC [read] | Beats, downbeat, drop detection, so cuts land on the music | `beats.py` |
| Mastering by reference | matchering | GPL-3 [read], ideas only | Average spectrum of the loudest parts and a bounded matching EQ (not yet built; see gaps) | none yet |
| Natural local voice | Kokoro (9.9k★) | Apache-2.0 [read]; weights [memory] | Per-line speed, punctuation prosody, voice blending | `voice.py`, `mood:` |
| Script prompts | MoneyPrinterTurbo, ShortGPT | [read] prompts; licences not confirmed, so ideas only | Strict output constraints, banned openers, search terms in narration order | `references/topic-to-video.md` |
| Research | gpt-researcher (30k★) | Apache-2.0 [read], ideas only | Sub-questions → sources → numbered citations → a reviewer pass that drops uncorroborated claims | SKILL step 2 |
| SKILL.md design | remotion-best-practices, hyperframes skill | [read] | A router (when X, load Y), short numbered hard rules, an explicit work loop | `SKILL.md` |
| Seamless Short loop | hassancs91/claude-faceless-shorts-creator | MIT [read], idea only; our code is our own | The last frame and last line lead back into the first, so the Short replays without a seam | `ending: loop`, `qa.py` (`loop ending`) |
| Public-domain and CC footage and photos | Internet Archive advanced search (key-less) | the API's `licenseurl` field; only CC0, public domain, CC BY, CC BY-SA are kept, never NC or ND | Movies and images with a licence link on a creativecommons.org page; items without one are `unverified` | `assets.py` (`archive` provider), `assets source` |
| Licensed cut-outs | rembg | MIT code [memory] | `isnet-general-use`; never the non-commercial default model | `assets cutout` |

## Evaluated and rejected, or postponed

| Project | Why |
|---|---|
| MusicGen | Weights are CC-BY-NC [memory]: not usable commercially. |
| ACE-Step (Apache-2.0 [read]), YuE, DiffRhythm | Need a GPU; impractical on a CPU-only PC. Library tracks and the synth score are better. Reconsider on a GPU. |
| F5-TTS | Code is MIT [read], but the weights are CC-BY-NC [memory]. Skip for commercial use. |
| Chatterbox | Now adopted as a local route; see [voice direction](voice-direction.md). MIT per its maker [read]; output carries a watermark. |
| Dia, Orpheus | GPU-bound [memory]. |
| Fish Audio Drama 3 | Top open-weight model in blind tests (November 2026 snapshot), but reported to need about 32-48 GB of NVIDIA memory, and its licence has a revenue cap [read]. |
| VibeVoice | Weights reported as research use only [read]. Not for commercial use. |
| OpenVoice v2 | Tone-colour conversion only; P3. |
| madmom, essentia | Non-commercial model files / AGPL [memory]. Ideas only; librosa is used instead. |
| openSMILE | Research licence [memory]. |
| Stable Audio Open, AudioLDM | Licence limits and GPU [memory]. Use CC0 packs and synthesis. |
| Real-ESRGAN (dormant), RIFE | Too slow on CPU [memory]. Use `lanczos` + `unsharp` from ffmpeg. |
| open_clip visual stock ranking | Feasible (~600 MB with torch [memory]). Only worthwhile if keyword ranking misses often. |
| GSAP | Free but not OSI open source [memory]. We use our own eases. |

## Worth adding next

- **Bounded reference-matching EQ:** 1/3-octave average spectra of a reference and our mix, with a correction of at most ±4 dB per band.
- **Lottie assets:** `lottie-web` (MIT [read]; stale since 2025) can be driven frame by frame with `goToAndStop(frame, true)`. Check each animation's own licence.
- **Sonniss GDC packs and Freesound CC0** for risers, paper and typing (Kenney has none). Verify each pack's terms before bundling.

## Limits of this research

Each project was read through a small number of files. Many items are marked [memory], and no project's claims were benchmarked here. Mixing numbers are standard practice checked against one source (HyperFrames), and they were not tested on physical phones; only a speaker simulation was used.
