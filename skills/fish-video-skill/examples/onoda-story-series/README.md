# Hiroo Onoda, two-part story Short series (9:16)

Past output and quality bar, not a template: set the direction from live `fishvideo trends` research first (see `examples/README.md`).

What it shows: a photo-led, two-part true story (Part 1 25.5 s, Part 2 27 s) with archive photos, labelled illustrative images, a glowing road and linked parts ("Part 2 is next").

- Recipe and theme: `story-short`. Built with the `glow-metaphor` style and "No theme" (`theme: none`); the nearest theme is `archive-doc`.
- Custom: `part*/scenes/custom.js` (photo cards with labels, leaflet confetti, dark overlays).
- Per part: `brief.yaml`, `storyboard.yaml`, `scenes/`, `post-text.txt`, `qa.md`, `frame-sheet.jpg`, `cover.jpg` (the approved cover), `sample-720p.mp4` (the whole Short at 720p). Shared: `credits.md` (all images with licence and author). Voice: AI narration; music original; SFX Kenney CC0.
- `qa.md` records the QA result of each original (PASS). Pacing notes (fast lines, short dead air) were logged in the project review, not in `qa.md`.

## Image licences
Public domain: Marcos photo (Malacanang Palace), USS Missouri surrender, surrender leaflet, ONI uniform plate (US Navy).
CC BY: Lindsay photo (Christine Maple, LA Times, CC BY 4.0), JASDF C-1 (CC BY 4.0), Palawan jungle (Vyacheslav Argenberg, CC BY 4.0), IJA sword (BrokenSphere, CC BY 3.0).
CC BY-SA 4.0: Lubang landscapes by Bahnfrend and Elmer B. Domingo. They were cropped, darkened and captioned, so these frames are adaptations; share them under CC BY-SA 4.0 with the credit in `credits.md`.

## Uncertain licence basis (left in the sample videos and cover)
- `Hiroo_Onoda_young.jpg` (cover of Part 1, both videos): tagged public domain, author unknown, Commons flags a personality-rights note.
- `Hiroo_and_shigeo_onoda_1944.jpg` (Part 1, the Mainichi family photo): public-domain claim relies on a 1974 Mainichi Shimbun publication.
- `47th_Infantry_Regiment_in_the_Philippines.png` (Part 1): public-domain claim, author unknown.
The three source files are NOT committed, but they are visible in `part1/sample-720p.mp4`, `part1/cover.jpg` and (the portrait, small) `part2/sample-720p.mp4`. If a rights holder objects, replace them in the videos.

## Gate result
`gate --stage script`: ready for both parts. Full `gate`/`gates` on copies: FAIL (19 and 18 problems) because the 12 and 11 photos are not committed, so every beat reports a missing file and "lacks a credit record". Nothing else failed.

## Reproduce
Copy a part's `brief.yaml`, `storyboard.yaml` and `scenes/` into `projects/<slug>/`, source your own licensed images (`fishvideo assets source`), then `gate` and `all`.
