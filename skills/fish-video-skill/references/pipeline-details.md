# Pipeline details (steps 0 to 10)

The long form of the numbered path in `SKILL.md`. Load the section for the step you are on; the strict path and its stop conditions live in `SKILL.md`.

You make one video from one conversation. It must reach the quality of the top Shorts dissected in [reference breakdowns](references/reference-breakdowns.md):
- something new on screen every ~1 s
- real assets with depth (texture, contact shadows, glow)
- type with a 3× hero-word contrast
- object-as-portal transitions
- a swish that lands *before* every move, risers that *end* on reveals, impacts on flash cuts
- a voice that sits on top of an audible music bed

A slideshow with a generic voice is a failure even when QA passes.

## Router: load the guide when you reach the task

Read only what the current step needs:

- The user gave only a word, or wants topic ideas, or you are writing the script → [topic to video](references/topic-to-video.md)
- Choosing a style, palette or look → [style recipes](references/style-recipes.md), `config/styles.yaml`
- An idea needs explaining, or choosing colours by mood → [diagram design](references/diagram-design.md)
- Writing any scene → [scene catalogue](references/scene-catalogue.md), including Motion rules and Camera
- Anything about music, SFX or levels, or "I can't hear the music on my phone" → [sound design](references/sound-design.md)
- Choosing or directing a voice → [voice direction](references/voice-direction.md)
- Free local voices (male or female, airy, soft, pace control, `voice setup|audition|check|redo`) → [local voices](references/local-voices.md)
- Captions and type → [captions & typography](references/captions-and-typography.md)
- A website or app on screen → [website-tour capture](references/website-tour-capture.md)
- A reference video to match → [reference breakdowns](references/reference-breakdowns.md), [reference-video analysis](references/reference-video-analysis.md), [trending analysis](references/trending-analysis.md)
- Reviewing frames (sheet, lint, guides, variants, palette, compare) or designing, checking and picking thumbnails → [frame design](references/frame-design.md)
- Platform sizes and limits → [platform specs](references/platform-specs.md)
- A long video that walks through stages (a roadmap, a learning path), or memes without copyright claims → [long roadmap videos](references/long-roadmap-videos.md)
- Memes (Indian and world), reaction clips, cue sounds, website screenshots, logos, icons, emoji, or the `meme` scene → [memes and real assets](references/memes-and-real-assets.md)
- Which open-source tool to reach for → [field guide](references/open-source-field-guide.md)

## Non-negotiable workflow

```
0 doctor ─▶ 1 INTERVIEW (all questions, once) ─▶ confirm ─▶ 2 research + trends + references (parallel)
  ─▶ 3 assets + screen capture + voice (parallel) ─▶ 4 storyboard (you write every word) ─▶ gate
  ─▶ 5 stills (look) ─▶ 6 render ─▶ 7 QA + REVIEW loop (fix, re-render, repeat) ─▶ 8 package ─▶ 9 final review ─▶ 10 clean (ask)
```

Rules:
- **One interview, at the start.** Every question that needs the user is asked in step 1, including voice and tone, colours, the screen steps, API keys (with how to get each one) and the optional extras to install. After `fishvideo interview <dir> --confirm`, you do **not** ask questions. Decide from the answers and the style recipe. Contact the user again only in these cases:
  - (a) an optional stop they chose in `checkpoints`
  - (b) a desktop recording they must perform; they agreed to it in the interview, and you tell them exactly when to start
  - (c) the final review
  - (d) permission to clean up

  If the user later says something different, follow the user.
- **Never write a script before the interview is confirmed.** `fishvideo script`, `all` and full `render` refuse until `fishvideo gate` passes.
- **Never ship template text.** The scaffold is a skeleton of TODOs. You write every on-screen word and every narration line fresh for this video, so the gate blocks TODOs, v1 stock phrases ("X, explained", "in 60 seconds", "Thanks for watching") and any line copied from `examples/`. Examples show structure, never content.
- **Explainers get a diagram.** Any `goal: explain` video needs at least one `diagram`, `whiteboard`, `neonline` or `split`-reveal mechanism scene. A list of bullets is not an explanation.

## Step 0: doctor

Setup (first time only) is in `README.md`: `npm install`, a venv, and `pip install -r requirements.txt`. Then run:

```bash
.venv/Scripts/python scripts/fishvideo.py doctor --keys      # Windows (macOS/Linux: .venv/bin/python)
```

Note which keys and extras are missing. You ask about exactly those in interview round 8.

> **Setup for the best result (do this, don't skip it):**
> - **Install the extras yourself.** If `doctor` shows a missing extra, install it into the skill's venv without making the user do it: `pip install "rembg[cpu]"` (cut-outs), `pip install kokoro soundfile` (natural local voices) and `pip install faster-whisper` (aligns the user's own voiceover). Also run `fishvideo assets sfx-pack` once if the SFX library is missing. Tell the user in one line what you are installing and why. Only skip an extra the user declines in round 8.
> - **Ask for the API keys.** They are **optional**: everything works without them through the free fallbacks. They do give the best result: ElevenLabs gives the most natural voices, Pexels/Pixabay give the most stock photos and video, Freesound gives the most SFX, and the YouTube Data API gives the trending charts. In round 8, ask for the ones that matter for this video, say how to get each one (free sign-up links are in `doctor --keys`), and accept "no" or "later" without pushing. Do this in the interview only, never once creation has started.

## Step 1: the interview (strict)

```bash
fishvideo new projects/<slug> --prompt "<the user's request, verbatim>"
fishvideo interview projects/<slug>            # JSON: the open questions, grouped in 8 rounds
```

The question bank is [config/interview.yaml](config/interview.yaml). It has 8 rounds and about 30 questions:

| Round | Covers |
|---|---|
| 1 | purpose |
| 2 | shape and style |
| 3 | colours, type, texture |
| 4 | voice, delivery, music, SFX |
| 5 | real assets and screen recording |
| 6 | content, facts, CTA, language |
| 7 | captions, thumbnail, approvals |
| 8 | API keys and extras |

**Only a word or an area?** Before round 1, generate 5 trending angles: `yt suggest`, `yt search --recent-days 30` and `trends` (haiku subagents, in parallel), following [topic to video](references/topic-to-video.md). Offer them as the `topic` question. The chosen angle drives everything after it.

How to ask:
- Ask **one round per `AskUserQuestion` call** (up to 4 questions), using the options exactly as listed. Recommended options come first. "Other" is always available.
- Free-text questions (`free_text: true`) go in a normal message for that round, together with the round's multiple-choice call.
- Skip a question only when the prompt already answers it unambiguously (`from_prompt` shows what was detected), and record it anyway.
- Record each answer: `fishvideo interview <dir> --set style=paper-collage --set platforms='["shorts"]'`. Answers map into `brief.yaml`: the palette goes to `brand.colors`, the mood to the score and tempo, the voice and delivery to the voice config and post chain, and the style to texture, pacing and motif.
- **Voice:** after rounds 4 and 6 (once the language and delivery are known), run `fishvideo voices <dir> --audition`. Give the user the file paths in `build/auditions/` so they can play them, and let them pick. This is still part of the interview.
- **Keys:** offer only the missing keys that matter for their answers. Explain how to get each one (the text in the bank) and what happens without it. If they paste keys, record them with `--set keys_paste=...`. Keys go to the skill's gitignored `.env` and are never echoed, logged or committed. If they choose extras, install them into the venv now (`pip install "rembg[cpu]"`, `kokoro soundfile`, `faster-whisper`).
- Finally, read `fishvideo interview <dir> --summary` back to the user. Ask for a plain "yes, go", then run `--confirm`.

## Step 2: research, trends and references (run in parallel)

Spawn these as parallel subagents. Model routing: **haiku** for fetch and lookup sweeps, **sonnet** for analysis and routine code, and you (**opus**) for the script, storyboard, design judgement and final review. Brief each agent with the project path and the exact output file it must produce. Subagents may not be able to write report files; then they return the text and you save it.

| Task | Command | Agent |
|---|---|---|
| Facts and sources | web search, then `fishvideo research <dir> --url ...` → `research/facts.md` | haiku |
| Trends | `fishvideo trends <dir>` (required, enforced by `gate`): recent results for the topic in its format, ranked by views per day, Shorts separate → `research/trends.json`, `trends.md` and the thumbnail contact sheet `trends-contact.jpg`; open the sheet, write the Analysis and `direction:` in `trends.md`; `--derive-theme` builds a project theme from the thumbnails; `--unavailable "<reason>"` only if search is down. Analysis only: never used in the video, committed or packaged | haiku |
| YouTube look-ups | `fishvideo yt search "<q>" -n 20 [--recent-days 30]`, `yt info`, `yt subs`, `yt suggest` | haiku |
| Reference dissection (each link the user gave, plus 1–2 top trending examples in the chosen style) | `fishvideo yt download <url> --purpose reference --project <dir>`, then `fishvideo dissect <dir>/reference/<file>.mp4 --out <dir>/reference/dissect --fps 4 [--vtt subs.vtt]`. Read **every** sheet, the spectrogram and `timeline.md`, then write `reference/analysis.md` with the nine sections of [reference-video analysis](references/reference-video-analysis.md) | sonnet (vision) |

From the dissections, take numbers: change rate, swish timing and level, voice-over-bed dB, duck depth, loudness, caption style. Write them into `brief.yaml → match:` so the storyboard and mix can follow them. **Copy craft, never content.**

## Step 3: assets, screen and voice (run in parallel)

**Real assets** (when `assets.policy` is `mixed`):
- Search: `fishvideo assets search <dir> "<noun>" --kind photo|video|music|sfx [--providers wikimedia,pexels]`. Open the previews in `assets/_candidates/` and look at them.
- Download what you pick: `fishvideo assets get <dir> <ids>`. Every file is logged to `assets/credits.json` with its licence.
- Make cut-outs: `fishvideo assets cutout in.jpg out.png` (rembg with `isnet-general-use`; never the non-commercial default model).
- Prepare b-roll: `fishvideo assets clip <dir> <file> <clip_id> --start S --dur S` gives frames for the `footage` scene.
- Get a CC-BY YouTube section: `fishvideo yt clip <url> <start> <end> <dest> --project <dir>`. It refuses non-CC videos.
- Licences allowed: CC0, PD, Pexels/Pixabay licences, CC-BY and CC-BY-SA (credited). Never NC or ND. Never a non-CC YouTube video, a reference video's footage, a logo you redraw, or a real person's likeness in a misleading way.
- One opt-in exception (2.3): memes and viral sounds have no verifiable licence. They are tier `unverified` and refused unless the user chose `viral` in the `memes` interview question (`memes.policy` in the brief) or you pass `--accept-risk` for that one file. Tell the user the risk (claim, mute, takedown). QA warns and the credits list each one as not verified. Details: [memes and real assets](references/memes-and-real-assets.md).

**Screen:**
- `website`: list the shots under `captures:` and run `fishvideo capture <dir>`. It films read-only in virtual time.
- `desktop`: `fishvideo screenrec record <dir> <shot> --seconds N [--window "Title"] [--scale 2]`. Before it starts, tell the user exactly which steps to perform. F8 drops a mark and F9 stops.
- `files`: `fishvideo screenrec import <dir> <shot> recording.mp4`.

All three produce the same capture folder. The `tour` scene (`frame: inset`) adds the glow cursor, click ripples and click SFX, a 1.6–2× zoom to the cursor, a spotlight and STEP cards. Record at scale 2 so zooms stay sharp.

**Music:**
- A library track: `assets search <dir> "<brief.music.search>" --kind music`, then `assets get`, and put the file in `assets/music/`.
- Or leave the synthesised score. Set `music.source: synth` to force it.

**SFX:** run `fishvideo assets sfx-pack` once (Kenney CC0). Add more with `assets search --kind sfx` (Freesound CC0) into `assets/sfx/<cue-type>/`.

**Voice:** write the narration (step 4), then run `fishvideo voice <dir>`. Re-run the storyboard so scenes re-time to the real clips. If the user recorded their own narration, run `fishvideo voiceover <dir> recording.wav` instead: it aligns the recording to the script with faster-whisper and cuts it per line. Without `faster-whisper`, transcribe elsewhere and add `--words words.json`.

**Emotion:** give each scene a `mood:` (`curious`, `tense`, `urgent`, `excited`, `warm`, `serious`, `reflective`, `triumphant`, `neutral`). It sets speed and pitch per line, and style on ElevenLabs. Punctuation shapes the delivery on every engine: `...` pauses, `?` and `!` lift, short sentences punch. Vary mood across beats: one flat tone for 40 seconds is the "generic voice" complaint. Silent stretches inside a line are cut automatically (`pacing.max_word_gap`).

**Music timing:** for a library track, run `fishvideo beats <track>`. Set the storyboard `bpm` to its tempo and `music.offset` so a beat or the drop lands on your biggest reveal.

**Screen recordings:** run `fishvideo screenrec tighten <dir> <shot>` to speed through idle stretches. Never make the viewer wait for a loading spinner.

## Step 4: storyboard (you write it)

Run `fishvideo script <dir>`. It scaffolds `storyboard.yaml` from the style recipe ([config/styles.yaml](config/styles.yaml), [style recipes](references/style-recipes.md)) as a beat skeleton full of TODOs. Its timings are placeholders. Then write it properly, in this order:

1. Replace every TODO: copy, params and narration. The table at the top of the [scene catalogue](references/scene-catalogue.md) lists the required params.
2. Write `brief.publish` and check the fields the interview cannot fill: `title`, `facts` (`{text, value, source}`), `sources`, `cta`.
3. Run `fishvideo voice <dir>`, then `fishvideo storyboard <dir>`. Only now are the scene lengths real. Anything timed in beats (`at`) is set against the spoken words *after* this step.
4. Run `fishvideo gate <dir>`.

**Variety.** Never use the same scene type twice in a row in a Short, and never three stats or charts in a row. A real photo must never appear unprocessed. Use `assets cutout` and a treatment, because a dull rectangle kills the frame.

**One character.** Choose one recurring object or figure before writing any beat: a phone, a box, a dot, a letter. Everything in the video happens to it, and it appears in every scene (`anchor` / `carry`, and `match` transitions). This is the clearest difference between trending videos and generated slideshows: see [trending analysis](references/trending-analysis.md).

**Diagrams evolve.** Keep one persistent element and let it re-label, grow or travel (`neonline` with `follow`, `diagram` with `morph`, camera push-throughs). Don't assemble unrelated static nodes.

**Beats.** Split the idea into 4–8 meaning beats: hook, claim, human moment, concept, escalation, turn, payoff, end. Use one scene per beat, and repeat beats for screen steps.

**Style bible lock.** Every scene uses:
- the same palette, one accent, one type family
- the style's motif
- rising intensity until the payoff

**Hook.** Frame 0 is already full: a subject, a title slam or a striking cut-out. Nothing appears before it (no logo, no fade-in). Within the first 1–2 s it delivers the hook kind the user chose.

**Change rate.** Something new every `pacing.change_every` seconds (0.75–1.2 s for Shorts): an element entrance, a camera move, a reveal or a word pop. Never hold a static frame for more than 2 s on a Short.

**Copy:**
- Narration runs about 3 words/s (`punchy`), 2.4 (`calm`) or 2.2 (`cinematic`).
- One idea per sentence. Concrete nouns.
- No "revolutionary", "seamless" or "leverage".
- Respell numbers and acronyms with `{shown|spoken}`.

**On-screen text** is a subset of the narration, at most 6 words per line, with one `*accent*` word.

**Transitions.** Prefer object-as-portal transitions (`zoom`, `flip`, `split`, `defocus`) and `flash` for impact cuts. Avoid plain `fade`.

**Sound comes from cues.** Scenes emit cues automatically. Add explicit `cues:` for story moments:
- a `riser` that ends on the reveal
- an `impact` on the title slam
- a `boom` on the payoff
- silence after the final hit when the style calls for it

**Script from the topic.** Follow [topic to video](references/topic-to-video.md): one-sentence summary, beats, hook, open loop, payoff, then read it aloud and cut 10%.

**Diagrams and theme.** Choose the diagram from the sentence (flow, anatomy, cycle, split, chart, zoom-in layers, lanes, architecture), reveal its parts in narration order, and put the accent on one element per beat. When the user picked "style default", choose the style, palette, music and delivery from the script's mood. All of this is in [diagram design](references/diagram-design.md), and the mood table is `config/styles.yaml → mood_map`.

**Facts.** Every number on screen or in the narration must be in `brief.facts` with a source; `factcheck` enforces this.

**Publishing copy:**
- 5 title options in `brief.publish.titles`, using the formulas from `research/trends.md`. Keep each ≤ 60 chars with the hook word first.
- `publish.description`, the first 2 lines of which are the hook.
- `publish.tags` (≤ 15) and `publish.hashtags` (3–5).
- The `thumbnail:` block.

The scene catalogue, with params and examples for every scene, is [scene catalogue](references/scene-catalogue.md). The motion and sound rules are in [sound design](references/sound-design.md), [pacing & music](references/pacing-and-music.md) and [captions & typography](references/captions-and-typography.md).

Then run `fishvideo gate <dir>`. It must say `ready`.

## Step 5: stills (look at them)

Run `fishvideo stills <dir> --scenes` for every platform and **open every still**. Check:
- depth: texture, shadows, glow
- hierarchy: 3× contrast between the hero word and small text
- the safe area: no text under the Shorts/Reels UI
- that the caption plate is legible on busy frames
- that nothing looks like a default template

Fix the problems and look again. If the user chose the `stills` checkpoint, show them now.

## Step 6: render

Preview the hardest 10 s first: `fishvideo render <dir> --platform shorts --scale 0.5 --fast --from 8 --to 18`. Then run the full render: `fishvideo render <dir>`.

The audio is **three stems**:
- **voice** at −16 LUFS
- **music** 10 dB under the voice, mid-carved and ducked about 6 dB while speaking, present from frame 0 and faded at the end
- **sfx**, made of real samples plus synth, never ducked, placed by cue: swishes 0.1 s early, risers ending on the cue, at most one SFX per 80 ms

The master is −12 LUFS with −1 dBTP on Shorts, Reels and TikTok, and −14 LUFS with −1.5 dBTP on the other platforms. The knobs are `mix:` in `brief.yaml`.

## Step 7: QA and the review loop

Run `fishvideo qa <dir>`. Fix every FAIL, and treat every WARN as a fix unless you can justify it to the user. Then run the review loop **at least twice**:

1. `fishvideo review <dir> --platform <p>` writes `REVIEW.md` (measured numbers and findings tagged P0/P1/P2) and three sheets in `build/<p>/review/`: beats at phone width, a strip around each cut, and the hook.
2. Open every sheet. Under "What I looked at", describe each beat frame in one sentence and name every object. **An object that needs explaining is a P0.** Name the weakest shot.
3. Write notes as `t=4.2s · where · problem → exact change`. Fix P0s and worthwhile P1s in this order: text, timing, detail.
4. Re-render only what changed, and repeat. Read `REVIEW.md` before changing anything.

Never score the video out of 10; a score finds nothing to fix. Where the numbers and your eyes disagree, trust the numbers. You cannot hear, so audio is measured with commands.

Also:
- Open each `build/<platform>/contact.png`.
- Run `fishvideo dissect build/<platform>/final.mp4 --out build/<platform>/self-check`. Compare its balance and event density with the reference numbers:
  - voice over bed of 6–14 dB
  - music audible in gaps (above −38 dBFS)
  - a swish within 0.15 s before most cuts
  - SFX density matching the chosen level
- Check `speaker translation` in the QA report. `build/<p>/phone-monitor.wav` is what a phone plays. If the music or SFX vanish there, fix the mix (see [sound design](references/sound-design.md)); never ship a mix that only works on headphones.
- Watch the first 3 s and the end. Would this hold attention next to the references? If not, go back to step 4.

## Step 8: package

Run `fishvideo package <dir>`. It produces `out/<date>_<slug>/` containing:
- `README.md` (the index and an upload checklist)
- `video/`
- `captions/`
- `thumbnails/` (1280×720 plus vertical covers)
- `metadata/` (titles, per-platform post text with chapters, sources and credits, tags, transcript, `credits.txt` with every licence and the AI disclosure, `metadata.json`)
- `qa/`

## Step 9: final review

Send the user:
- the path to `out/<date>_<slug>/`
- the main video file
- the thumbnail
- the 5 titles
- the measured loudness and mix balance
- anything still open, such as an estimated voice or a WARN

Ask for approval or changes. On changes, edit and re-render only what changed.

## Step 10: clean up (only with permission)

After the user approves the final video:
1. Run `fishvideo clean <dir>` (a dry run). It lists what would be deleted (`build/`, reference downloads, unpicked candidates, raw pages) and what is kept (brief, storyboard, the assets used with their credits, research notes, and `out/`).
2. **Ask the user** whether to delete it, and give the size.
3. Only on a yes, run `fishvideo clean <dir> --yes` (add `--keep-voice` if they may re-render).

Never delete without that yes.

## Hard rules

- Never invent facts, numbers, quotes, customers or logos. Unsourced numbers fail the build.
- References are for analysis only. Never cut a reference's footage, music or voice into the video. Downloads stay in `reference/` and are cleaned afterwards.
- Every third-party asset is in `assets/credits.json` with its licence and risk tier. Licence-safe projects hold only licences that allow commercial reuse; opted-in non-safe assets are listed apart. The package credits all of it.
- Film websites read-only: no logins, no form submits, no purchases, no private data. Desktop recordings never log typed text, only modifier combos.
- Keys live in `.env` and environment variables only. Never print or commit them.
- Never max out the user's machine. Renders run below normal priority under a CPU cap (`FISH_CPU_LIMIT`, default 60%), so they take longer but the PC stays usable. Don't raise it unless the user asks. Run heavy jobs one at a time, as tracked background tasks, so nothing is left running.
- Scene code is deterministic: no `Math.random`, `Date`, CSS animations or rAF.
- Do not upload or publish anything. The deliverable is the local folder.
- `--no-gate` exists for the test suite. Never use it for a user's video.

## Failure modes (v1 lessons)

| Symptom | Cause | Fix |
|---|---|---|
| Every video says "X, explained… in 60 seconds" | The v1 scaffold wrote copy | Scaffold is skeleton-only, and the gate blocks stock or example lines |
| Questions trickle in mid-render, or none are asked | There was no interview contract | One 8-round interview, confirmed before scripting |
| BGM inaudible; risers and clicks vanish | One bus, −5 dB bed, ratio-6 duck that also ducked the SFX | Three stems: music −10 dB re voice with a 6 dB duck; SFX unducked |
| Swishes feel late and mushy | 0.55 s whooshes placed on the cut | 150 ms swish, starting 0.1 s before the move |
| Looks flat, like a template | Vector boxes only, no assets, no texture | Real cut-outs (`assets cutout`), `texture: paper/grain`, contact shadows, glow; collage/split/neon scenes |
| A generic narrator | Fixed default voice | A delivery preset plus auditions in the interview, with ElevenLabs, Kokoro and edge Multilingual voices |
| A planned sound never plays | Explicit `cues:` were dropped before the stage | Fixed; QA now fails if a hand-placed cue is missing. Measure the SFX stem to confirm |
| Half the frame sits empty, QA still passes | Technical checks cannot see it. The `bare frame` check is a heuristic (twice a second, 1.5 s): it misses busy backgrounds and cannot tell a title card from a gap | ALWAYS tile the video and open the frame sheet, whatever `qa` says |
| Imported voiceover lost its pauses | `pacing.max_word_gap` trims them | Raise it for a performance you approved |
| Soft zooms in screen tutorials | Recorded at 1× | `screenrec --scale 2`, `capture` at DPR 2 |
| Captions unreadable over busy frames | No plate | `captions.style: pop` adds an automatic 40% plate |
| Plus every v1 renderer issue | | See [website-tour capture](references/website-tour-capture.md) (virtual time, fonts, decode, faststart, loudnorm) |

## Files

- `scripts/`:
  - `fishvideo.py` (CLI)
  - `interview.py` (interview, gate, approvals, auditions)
  - `youtube.py`, `trends.py`, `assets.py`, `screenrec.py`, `dissect.py`
  - `sfx.py` (sample SFX)
  - `music.mjs` (score plus synth SFX stem)
  - `render.py` (stem mix)
  - `qa.py` (including mix balance)
  - `package.py`, `clean.py`
  - `research.py`, `reference.py`, `storyboard.py`, `voice.py` (ElevenLabs, edge-tts, Kokoro), `captions.py`, `fvcore.py`, `fvnet.py`
  - the stage: `stage/` (scenes, transitions, textures, captions)
- `config/`: `interview.yaml`, `styles.yaml` (style bibles, palettes, music moods), `voices.yaml` (voice shortlist, delivery presets), `defaults.yaml`.
- `references/`:
  - [reference breakdowns](references/reference-breakdowns.md)
  - [topic to video](references/topic-to-video.md)
  - [diagram design](references/diagram-design.md)
  - [sound design](references/sound-design.md)
  - [style recipes](references/style-recipes.md)
  - [scene catalogue](references/scene-catalogue.md)
  - [memes and real assets](references/memes-and-real-assets.md)
  - [pacing & music](references/pacing-and-music.md)
  - [captions & typography](references/captions-and-typography.md)
  - [voice direction](references/voice-direction.md)
  - [platform specs](references/platform-specs.md)
  - [reference-video analysis](references/reference-video-analysis.md)
  - [website-tour capture](references/website-tour-capture.md)
  - [storyboard templates](references/storyboard-templates.md)
- `sfx/library/`: Kenney CC0 interface, impact and UI packs plus `index.json`.
- `examples/`: `genai-roadmap-long/` (long roadmap explainer, 44 s excerpt), `onoda-story-series/` (two photo-led story Shorts) and `gta6-short/` (typographic Short). Each has a README with its recipe, licences and gate result; watch the sample video and read the `storyboard.yaml`. Structure only, never reuse their lines.
- `tests/`: unit tests (`test_units.py`, `test_tools.py`), node tests, and e2e smoke renders.
