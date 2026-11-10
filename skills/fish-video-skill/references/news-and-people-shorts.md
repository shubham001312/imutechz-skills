# People, news and fact Shorts

The format: a two-part series (Part 1 opens a question, Part 2 answers it) about real, recent events involving well-known people (actresses, actors, athletes, creators) or a surprising fact. Every frame carries a real photo or real footage, with layered elements on top. Start it with `fishvideo new <dir> --recipe news-short`. The scene is `newsstory` (see the [scene catalogue](scene-catalogue.md)).

Learned on four Shorts (two stories, two parts each). The rules below are the ones that changed the result.

## 1. Length: under 25 seconds

Script about 20-22 s of speech per part, then measure the narration before you render: `ffprobe narration.wav`. Shorts that ran 34-52 s were rejected and had to be cut twice. Cutting is cheap if each sentence was voiced separately (the voice studio does this): drop whole sentences, rejoin, speed up by at most 1.1x with `atempo`, re-transcribe.

## 2. Pick the story: fame first, then a provable conflict

1. **The person.** Pick names the audience already searches for. An award-trivia story about a lesser-known actor lost to "a famous person + a conflict" every time.
2. **The conflict.** What gets watched is a person and a tension: someone did or said something to them, or they said something surprising. A statistic is not a hook.
3. **Freshness.** Prefer the last 3 months, and say the date on screen. If the story is older, say so and give what happened next.
4. **Provable.** Before scripting, open every source page itself (not a search snippet) and copy quotes verbatim. Search snippets merged facts from different stories more than once.

Research tools: `fishvideo yt search "<name> #shorts" -n 40` sorted by views, filtered to ≤ 90 s, shows which angles get watched for that person (fan edits and brand ads rank high: read the pattern, not the top row). `fishvideo trends`, `fishvideo memes trending`, and a web search for `"<name>" <month> <year>` complete the picture.

## 3. Honesty rules (they protect the channel)

- **Rumours are labelled as rumours, out loud and on screen.** "Unnamed reports blamed…", an UNCONFIRMED stamp, then what *is* confirmed. Never state a feud, an affair, an illness or a motive as fact.
- **Say who did not name whom.** If a director's post "names nobody", the script says so.
- **Quote, do not paraphrase,** and put the outlet and date in the quote card's head.
- **Hedge the absence of evidence.** "We could not find a public answer from her" is true. "She stayed silent" may not be.
- **Do not imply a link with pictures.** If a quote is about "male superstars" and names no one, do not put specific actors' photos next to it.
- **Footage that is not of the event says so:** `label: "VIDEO: WEF DELHI 2017 · NOT ABOUT THIS"`. Keep it muted, so nobody's words are put in their mouth.

## 4. Images

- **Source:** Wikimedia Commons (`assets search <dir> "<name>" --providers wikimedia`). Read each file page for the licence and the date. Prefer festival and premiere photos from the last two years: they are recent, colourful and openly licensed (CC BY / CC BY-SA). Never NC or ND.
- **Look at them** on a contact sheet before using them. Reject a picture with an odd shadow, an unflattering moment, a misleading object (a Saturn Award trophy in a video about the Emmys), a watermark or a heavy logo wall.
- **Framing:** faces, not bodies. Crop to the face and shoulders (`pos` and `z0`/`z1` on the slide). A red-carpet clip can drift onto a low neckline when a scene is shortened: open the frames again after every cut.
- **Size:** downscale every photo to about 1300 px on the long side before rendering. 5-8 MB festival PNGs slow every browser and push it toward the capture failure in section 8.
- **Labels:** every photo of a person says who, where and when (`"SYDNEY SWEENEY, TIFF 2024"`).
- **Credits:** `assets get` logs them; `package` lists them; the post text links every file page.

## 5. Video (real footage)

- **Search** with `fishvideo yt search "<name> interview" --cc`: YouTube's Creative Commons filter, with each result's licence re-read and kept only if it says Creative Commons (`channel_verified` is shown too).
- **Check that the uploader owns the footage.** A CC tag on a re-upload is not a licence. Good sources: the outlet's own verified channel (World Economic Forum, MTV UK) and journalists' own interviews (for example Margaret Gardiner). Red-carpet B-roll channels are a judgement call: say so in the review.
- **Preview** a low-resolution copy and make a contact sheet (`memes sheet <video> --every 10`) to find usable seconds: the person alone, facing camera, no interviewer.
- **Cut** 6-8 s (`yt clip <url> <start> <end> <dest> --project <dir>`, which refuses non-CC videos) and extract frames at the default 1080 px or at most 1280 px wide (`assets clip`). A 1920 px extraction doubles browser memory for no visible gain in a 9:16 crop.
- **Use** at most 1-2 clips per part: a clip is proof the person is real and alive on screen, not wallpaper.

## 6. Memes: real ones, matched to the beat

Emoji stickers read as filler. A real reaction meme that matches the beat (shock, side-eye, "wait, what", popcorn, applause) reads as a joke the viewer recognises.

1. Write the beat's reaction in a word or two ("shocked", "side eye", "popcorn", "this is fine").
2. Find it: `memes templates <dir> "<reaction>"` (Imgflip; **unverified** tier: needs `memes.policy: viral`, which only the user can choose) or `memes films <dir> "<reaction>"` (public-domain film; **safe** tier). Register files you bring with `memes add`.
3. Place it as a sticker in the scene's `fx`: `{kind: meme, src: assets/meme/x.png, word: "<spoken word>", x: .82, y: .40, w: .32, top: "ME READING", bottom: "THE COMMENTS"}`.
4. One meme per reaction beat, about one every 5-8 s in a 20 s Short, never the same gag twice in a video (`memes lint` warns). Emoji (`kind: emoji`) are the fallback only when the brief says no memes or nothing fits.
5. Never use a meme of a real person in a way that comments on the people in the story.

## 7. The frame: how the layers work

Each `newsstory` beat stacks, back to front:

| layer | what it does | motion |
|---|---|---|
| slide | the real photo, footage, a split of two faces, or polaroids on a blurred ground | slow push-in (`z0`→`z1`), cross-cut on a spoken word; footage ping-pongs so a short clip never jumps |
| scrim | a light gradient so text reads without hiding the faces | none |
| tag | PART 1 / PART 2 chip | static |
| lines | 1-3 short headline lines in a bold display face, two-tone | pop in on the spoken word: scale 1.32→1 in 0.18 s; `hit: true` adds an impact sound |
| fx | meme stickers, quote cards, stamps, chips, a flash | memes and emoji pop with an overshoot and a gentle wobble; cards slide up 70 px; stamps slam from 1.7× with a tilt; chips scale in; the flash fades over 4 frames |
| captions | the word-pop captions from the pipeline | below y 0.69 of the frame |

Rules: frame 0 already shows a face and the hook. A new picture or element every 1-2 s. Keep fx at y ≤ 0.66 so they never cover captions. The mystery split (`mystery: true` blurs both faces) is the strongest Part 1 ending. Every element lands on a spoken word (`word`), so it changes with the voice, not on a timer.

## 8. Rendering: what broke and how it is handled

- **Parallel browsers can fail screen capture** (`Page.captureScreenshot: Unable to capture screenshot`) on image-dense scenes, even with memory free. The same frames render cleanly with one browser. `render` now retries with one browser automatically. Expect about 0.3 s per frame: a 24 s Short takes about 4 minutes.
- **Never render two projects at once** on one machine. That multiplies the browsers, and every render fails.
- **`yt clip` range downloads** can crash inside ffmpeg (exit -11). `yt clip` now downloads the whole video once and cuts it locally instead.
- **After every script cut, re-open frames.** Shortening a scene changes which second of a clip is on screen, and anchors on deleted words fall back to fixed times (photos arrive late, leaving a blurred gap). Prefer `at` for collage items in short scenes.

## 9. Package

Each part ships with a cover (the hook frame, 1080×1920), a title that restates the conflict, a description with the sources and every credit, tags for the names and the show or film, `#shorts` plus the names, and an AI-voice disclosure. Part 1's description gets a line for the Part 2 link after upload. Run `fishvideo package`, then read the post text yourself.
