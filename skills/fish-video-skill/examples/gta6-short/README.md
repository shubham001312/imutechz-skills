# GTA VI download size (Short, 9:16)

Past output and quality bar, not a template: set the direction from live `fishvideo trends` research first (see `examples/README.md`).

What it shows: a 28.5 s typographic Short with no photos or footage: two numbered tips, a storage bar, a quoted blog line, a date stack and a closing question. Visuals are drawn by custom scenes in paper-collage style.

- Recipe and theme: closest is `bold-short` / `bold-shorts`; it was built with the `paper-collage` style and "No theme" (`theme: none`).
- Custom: `scenes/custom.js` (calendar, loading bar, storage bar, date tags, stacked spines).
- Files: `brief.yaml`, `storyboard.yaml`, `scenes/`, `post-text.txt`, `credits.txt`, `qa.md` (PASS on the 1080p original), `frame-sheet.jpg` (also serves as the thumbnail), `sample-720p.mp4` (full Short, 720p).

## Licence check
No Rockstar art, trailer frames, logos, box art or other third-party images are in the video or stills: every frame is typography and drawn shapes (checked on the frame sheet; `assets/` was empty). Text-level material only: the name "GTA VI", figures and dates from the PlayStation Blog (3 Nov 2026) and one short quote ("Get ready by clearing a minimum of 212GB of storage space on your PS5."), cited in `brief.yaml`. Game and console names are trademarks of their owners. The quote and facts are reporting, not a licence grant. Music is original; the voice is AI-generated.

## Gate result
`gate --stage script`: ready. Full `gate` on a copy: FAIL (14 problems): the imagery gate (0% real images, text-led) because the Short predates it and did not declare `visuals: {mode: abstract}`, plus two "narration copied from an example" hits that only appear because the copy matches this example itself. It is kept as the typographic style reference.

## Reproduce
Copy `brief.yaml`, `storyboard.yaml`, `scenes/` into `projects/<slug>/`, then `fishvideo all`. For your own topic, rewrite the lines and facts.
