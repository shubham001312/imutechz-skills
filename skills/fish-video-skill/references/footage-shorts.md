# Footage Shorts (`fishvideo footage`)

A Short cut from **real footage**: launch videos, news clips, product demos, b-roll, lab footage, screen recordings. It's
for tech facts, AI-model news, free-tool lists and "your phone can do this" Shorts, where the proof is something the
viewer can see. The stage recipes draw motion graphics; this pipeline cuts video.

It was built and tested on a batch of ten ImuTechz Shorts, each 20-27 s, all passing QA. Its rules come from what that
channel's owner approved and rejected:

- **Visuals are the hook, not text.** Viewers don't read. Every beat gets a new real shot, with logos, objects, arrows,
  rings or one counter over it. There are no sentence stamps on every beat. On-screen words are at most a big number or
  a 1-2 word label, a few times per video.
- **No burned-in captions** (`captions: false`, the default). YouTube, TikTok and Reels have their own CC, so upload
  `out/captions.srt` instead.
- **A proper video, not a motion-graphics slideshow.** A video that is all UI cards on a flat colour gets rejected.
  Cards are for the few beats that must show a screen.
- **The house voice** is the fish.audio public voice "calm storyteller male": deep and measured, never hyper.
  - Hear it in `assets/voices/fish-calm-storyteller.mp3`.
  - Its settings are reference_id `e686ae649ee44f219a108aacba206c1a` and model `s2.1-pro`.
  - At speed 1.1-1.12 it reads about 3.1 words per second.
- **The thumbnail is the insider cover:** one big real picture on top, a small lead line, one huge keyword and a black
  chip. It is drawn by `fishvideo thumbnail`.

## Rights

Third-party clips (YouTube launch videos, news, creators) are the channel owner's call: use them only when the owner asks for real footage, credit every clip, logo and track in `meta.sources` (it becomes `out/sources.txt`), and tell the owner which music is likely to be claimed. Prefer CC0 / CC BY stills and NASA footage where they show the thing as well.

## The path

1. **Topic and facts.** Pick a modern tech *fact* rather than history or a news recap. AI-model facts are fine. Verify
   every number on the web and list the source under `meta.sources`.
2. **New project.** `fv footage new projects/<slug>` writes `spec.yaml` from `templates/footage-spec.yaml`.
3. **Script.** Write about 3 words per second, so 65-80 words for 22-26 s.
   - Keep the first line under 10 words.
   - Put one `{anchor}` before each beat; one beat is 1-2.5 s.
   - Write numbers as words, with the shown form after a bar: `[eighteen percent|18%]`.
   - End on a question or a loop.
4. **Footage.**
   - Search with `fv footage yt search "<what the beat shows>"`, then fetch with `fv footage yt get projects/<slug>/assets <id> ...`.
   - Get logos as official SVG renders from Wikimedia Commons, using `fv footage commons`, `fv footage get` or
     `fv assets logo`.
   - Get stills and space clips from `fv footage nasa`.
   - Prefer the source's own channel, such as the company's launch video.
   - Skip clips with watermarks ("PREVIEW"), burned-in subtitles or talking heads that compete with the voice.
5. **Pick in-points by looking.** Run `fv footage sheet assets/yt-<id>.mp4 /tmp/s.jpg --step 2` and open the sheet.
   Never guess an `in:`, because the wrong second lands on an ad, a black frame or a title card.
6. **Voice.** `fv footage voice projects/<slug>` makes the fish.audio TTS (FISH_API_KEY in `.env`). Whisper then times
   each word, and difflib aligns the words to the script, which gives every anchor's time. Read the `HEARD:` line: it
   must match the script.
7. **Spec.** Add one shot per anchor, overlays (visual ones) and SFX on the cuts. See the reference below.
8. **Render, QA and look.**
   - Run `fv footage render projects/<slug>` (add `--preview` for a fast half-size pass), then `fv footage qa projects/<slug>`.
   - QA fails on any of these: a length outside 15-30 s; any 0.5 s window with mean frame difference below 1.0 (a static
     slide); median motion below 2.0; or a transcript ratio of 0.8 or less.
   - Then OPEN `build/sheets/final.jpg`. The numbers can't see a frame that is wrong but moving, such as an ad, a black
     frame or a stick-figure slide.
9. **Package.** Write the `thumbnail:` block, then run `fv footage package projects/<slug>`. Open both thumbnails.
10. **One command** for steps 6-9 once the spec is right: `fv footage all projects/<slug>`.

## spec.yaml reference

**Top level**

| key | meaning |
|---|---|
| `title`, `speed` (1.1-1.12), `tone` | Tone is the bracket cue for the whole read: calm, confident, excited or serious. |
| `voice` | Optional: `{reference_id, model, temperature, top_p}` replaces the house voice. |
| `script` | `{anchor}` marks a timing point. `[spoken words|SHOWN]` sets the caption text. |
| `music` | `{file, start, gain (-18..-22), duck (-7), fade_in}`. Start at the drop: find it by RMS or by ear. |
| `vignette`, `contrast`, `sat`, `look` | The global grade. `look` is one of none, cool, warm, teal, vintage or bw. |
| `captions` | Default false. When true: `caption: {y}`, `cap_chars`, `cap_units`. |
| `tail` | Seconds after the last word (default 0.45). |
| `qa` | `{min_len, max_len, motion_min, motion_median, transcript}` |

**Shots**

`shots:` gets one entry per anchor (`at:`), and a shot runs until the next one starts.

| key | meaning |
|---|---|
| `src`, `in`, `rate` (0.8-1.2), `reverse` | The clip and its playback. |
| `fx`, `fy`, `fx1`, `fy1`, `z0`, `z1` | Cover-crop focus and a push from zoom z0 to z1. For motion, push 1.1 to 1.4. |
| `shake` | Camera shake. |
| `card`, `card_w`, `card_y`, `float` | A floating card: `card: [l, t, r, b]` is the crop to float. |
| `bg` | The card's background: `blur` or a colour. |
| `bg_seq`, `bg_seq_alpha`, `bg_spin` | An animated logo frame sequence behind a card. |
| `trans` | whip, flash, glitch, dip, zoom or cut. |
| `look`, `sat` | Per-shot grade. |

**Overlays**

`overlays:` entries are `{type, at, until | hold, x, y, anim: pop | slam, ...}`.

| type | use it for |
|---|---|
| `image` | Logos and objects: `src`, `w`, `plate: true` with `plate_color` for a dark logo on dark footage, `spin`. |
| `imgseq` | An animated mark from a folder of PNG frames. |
| `counter` | The key number: `from`, `to`, `prefix`, `suffix`, `decimals`, `dur`, `label`. |
| `ring`, `arrow`, `beam` | Point at the thing in the shot. |
| `split` | A two-sided comparison: `sides: [{value, label, color}]`. |
| `spectrum`, `bars`, `clock` | Science visuals. |
| `stamp`, `tag`, `card` | Words. Use sparingly: text is not the hook. |

**SFX and packaging**

| key | meaning |
|---|---|
| `sfx` | `{at, file: sfx/s-<name>.wav, gain, dt, dur}`. The synth set is s-whoosh, s-boom, s-hit, s-riser, s-tick, s-glitch, s-pop, s-sweepdown, s-heartbeat, s-zap and s-thunder; `fv footage sfx` builds it, and it is made on first use. |
| `thumbnail` | `{lead, title, mid, chip, hero: {video, t, crop, kind: card|cutout, cut, color, ar} | logos: [...]}`. See `scripts/footage_package.py`. |
| `meta` | `{titles: [5], description, hashtags, tags, pinned_comment, sources}` |

## Craft notes from the batch

- **Motion:** QA flags static UI cards, so push them (z 1.0 to 1.3), float them, or put an animated logo sequence
  behind them. A shot under 1 s still needs a push.
- **Transitions:** whip on most cuts, flash on reveals, glitch for "wrong / hidden" beats, and zoom into a number.
- **Logos:** use official SVG renders, never redrawn ones. Give a dark logo on dark footage a plate (`plate: true`). A
  wide wordmark gets a rounded rectangle plate automatically.
- **Real demos beat claims.** In the QR Short, the code in the video was generated with segno, damaged frame by frame,
  and decoded by zxing on every frame. The video states the threshold that was measured (18%), not the spec-sheet 30%.
- **Music:** NCS tracks are Content ID-safe on Shorts. Film scores and major-label tracks are usually claimed, so say so
  in the delivery.
- **Numbers:** the narration says the number and the counter shows it. One counter per video is plenty.
