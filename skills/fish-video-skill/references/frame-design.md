# Frame design and thumbnails

Real tools for looking at a frame and for making the picture people click on. All of them work on
stills (never a full render) and write into `build/`.

## Frame tools (`fishvideo frame ...`, scripts/design.py)

| command | what it does |
|---|---|
| `frame sheet <dir>` | one hero frame per scene with its id, time and type: `build/<p>/design/sheet.png`. Read it before approving stills. |
| `frame lint <dir> [--scene id] [--strict]` | design QA per scene: names the element and a fix. Writes `build/<p>/design-lint.md`. |
| `frame guides <dir> --scene id [--bands shorts,reels,tiktok]` | the still with the safe area, action/title-safe, thirds and each platform's UI bands drawn over it. |
| `frame variants <dir> --scene id --vary palette\|texture\|type [--apply N]` | the same scene in several looks side by side, numbered. `--apply N` writes the choice to `brief.yaml` (comments in it are not kept; the file is rewritten) and rebuilds the timelines. |
| `frame palette <image or video> [--write <dir>]` | dominant colours, and a proposed background, ink and accent with their contrast ratios. `--write` puts them in the brief. |
| `frame compare <a> <b> [--at 2,8]` | before / after sheet of two stills (or two videos at the same times) with a difference map and the changed regions boxed. |

`frame lint` joins two sources: the stage's DOM (`scripts/designprobe.mjs`: every visible text, its box,
size, weight and declared colour) and the pixels of the still. Findings:

| kind | meaning | default threshold (`RULES` in design.py) |
|---|---|---|
| `low-contrast` | WCAG ratio of the text against the pixels behind it | 3:1 large text (>= 40 px at 1080), 4.5:1 otherwise |
| `busy-background` | the median passes, the worst tenth of the background does not | 2:1 |
| `flat-hierarchy` | hero text under 1.5x the small text (the style bible asks about 3x; under 2.5x is a note) | 1.5 |
| `too-many-sizes` | more than four type sizes in one frame | 4 |
| `wall-of-text` | too many words on screen, or one element with a sentence | 24 land, 18 square, 16 port; 12 per element |
| `off-palette-text` | a coloured text that is neither in the palette nor set by the scene | delta E 22 |
| `no-accent` | the accent is absent from the frame (a note) | 0.15% of the frame |
| `empty-quadrant` | a quarter of the frame is flat | greyscale std 3 |
| `edge-crowding` | text nearer than 2.5% of the short side to an edge | |
| `text-collision` | two text blocks of different sizes overlap | |
| `stage:*` | the stage's own lint: `too-small`, `outside-safe-area`, clipping, overlap | per-platform `min_text_px` |

Every finding is advice: `frame lint` exits 0 unless `--strict`, and the QA row is a WARN, never a FAIL.
A project can change a threshold with `brief.design.lint: {max_sizes: 5}` and silence a kind with
`brief.design.lint.ignore: [empty-quadrant]`.

## Thumbnail tools (`fishvideo thumb ...`, scripts/thumbs.py + scripts/stage/scenes/thumbs.js)

1. `thumb make <dir> --variants 5` draws distinct layouts through the stage at 1280x720 (PNG under 2 MB,
   else a JPEG of the same picture) into `build/thumbnail/variants/`, plus two vertical covers per 9:16
   platform in `build/thumbnail/covers/`, and a labelled `variants-sheet.png`. The layouts are `subject`
   (big words and a cut-out), `caption` (a frame with the words low and left), `number` (one giant
   figure, needs `thumbnail.number` or a `stat` scene or a figure in the title), `split` (before / after)
   and `frame` (the best frame in a card). Frames are the video's own scenes, scored for detail, colour,
   contrast and emptiness. Storyboard `thumbnail:` params feed them: `title`, `accent`, `kicker`,
   `badge`, `image`, `number`, `before`, `after`, `layout` (which one leads). Two more layouts are drawn by
   the required `fishvideo thumbnail` step: `road` (the house design) and `insider` (the light cover of
   kinetic-explainer videos: off-white canvas, one hero on top or left, a small lead line, one huge black
   keyword, a black chip with white type, scattered accent asterisks). `insider` is used when
   `thumbnail.layout: insider`, or when no layout is given and the recipe is `kinetic-explainer` (or the
   theme `insider-light`); every other video keeps `road`. Params and examples: recipes-and-themes.md.
2. `thumb check <dir> [--all] [--file f]` measures: file size and shape (the only FAILs), brightness,
   tonal range, saturation, the bottom-right corner a feed covers with the duration, word count (main
   text only; 6 or fewer), and the main text at 320x180 and 168x94: its size in px, and its contrast
   after shrinking (WCAG, on the downscaled picture). Results: `build/thumbnail/check.md|json`.
3. `thumb sheet <dir>` makes `feed-light.png` and `feed-dark.png`: the variants among neutral grey
   placeholders at real display size, with a fake duration stamp. It imitates no platform's branding.
4. `thumb pick <dir> N [--cover M]` records the choice in `build/thumbnail/pick.json`. `package` ships
   the pick as `thumbnails/thumbnail-1280x720.<png|jpg>`, plus `thumbnail-variants.png`,
   `thumbnail-feed-*.png`, `thumbnail-check.md|json` and each platform's frame-lint report.
5. `thumb cutout <image> [--outline 10] [--glow 34] [--color #hex]` removes the background (`assets
   cutout`, rembg), adds an outline and a glow in the brand accent and writes `<name>-glow.png`. Use it
   with `thumbnail: {image: assets/x-glow.png, baked: true}`.

Thresholds a thumbnail is held to (LIMITS in thumbs.py; the display sizes are assumptions about how feeds
show thumbnails, not measurements of any one platform): main text at least 16 px high at 320 wide and 9 px
at 168 wide, 3:1 contrast after shrinking, mean brightness 0.14 to 0.82, tonal range 0.45.

`qa` adds a `frame lint` row per platform and a `thumbnail` row per variant checked; `all` runs
`thumb make` before QA when no variants exist. New findings are WARN unless a fact is wrong (size, shape).
Add a thumbnail layout the way you add a scene: [scene catalogue](scene-catalogue.md) (a pure function of
time, text inside `c.safe`, bottom-right corner left free).
