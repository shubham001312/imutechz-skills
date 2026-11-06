# GenAI engineer roadmap (long explainer, 16:9)

Past output and quality bar, not a template: set the direction from live `fishvideo trends` research first (see `examples/README.md`).

What it shows: a 9:15 YouTube explainer built from a public roadmap article: hook pile, roadmap map, one scene per step, meme beats from silent-film clips, SFX and an original synthesised score. The full film is 9:15 (555 s, 67 scenes); this folder ships only a 44 s excerpt.

- Recipe and theme: `roadmap-explainer`. It was built with "No theme" (`theme: none`, the classic `neon-diagram` style with the `neon-amber` palette); the nearest theme is `tech-dark`.
- Custom: `scenes/custom.js` (the footage-meme scene, flow, cards and hourglass scenes). Everything else is stock scenes.
- Files: `brief.yaml`, `storyboard.yaml`, `scenes/`, `post-text.txt`, `credits.txt`, `qa.md` (PASS on the 1080p original), `frame-sheet.jpg`, `thumbnail.jpg` (approved designed thumbnail), `sample-excerpt-720p.mp4` (0:00-0:14.5 plus 0:24.5-0:54 of the film, joined; 720p).

## What appears in the excerpt, and the licence of each
- Narration: AI-generated voice. Music: original, synthesised for this video. SFX: bundled with the skill.
- Silent-film clips (Buster Keaton, "Cops" 1922 and "Neighbors" 1920, Wikimedia Commons): public domain, see `credits.txt`.
- Sad trombone (CC BY 4.0, Sad Tromboner), laughter (CC BY 3.0, lonemonk, freesound) and applause (CC0, Sandermotions): attribution in `credits.txt`. Whether they are audible in the excerpt depends on the cut.
- Website screenshots (reduced, shown as tiles in the hook and roadmap scenes; from the file names, pages of langchain.com, huggingface.co, ollama.com, llamaindex.ai, scikit-learn, Pinecone, promptingguide.ai, AWS Bedrock and the GeeksforGeeks roadmap article): these are third-party pages with no licence, shown small as commentary on tools the film names. The 10 s scene that makes the article screenshot the main visual is cut out. This is an unlicensed-screenshot risk; the screenshot files themselves are not committed.
- Thumbnail: product logos (OpenAI, Anthropic, Google Gemini, Meta, LangChain, Hugging Face, AWS). These marks belong to their owners and are used only to name the tools covered.
- Source article: GeeksforGeeks "Roadmap to Generative AI" (facts and order only, no text copied).
- `credits.txt` lists six credited assets; the 21 screenshots had no credit records.

## Gate result
`gate --stage script`: ready. Full `gate` and `gates` on a copy: FAIL (179 problems). Cause: the images (screenshots, photos) are not committed, so every beat reports "does not exist" and "lack a credit record"; the project predates the credit-record rule. The film itself passed its own QA at the time (`qa.md`).

## Reproduce
Copy `brief.yaml`, `storyboard.yaml` and `scenes/` into `projects/<slug>/`, fetch your own images with `fishvideo assets source`, then `fishvideo gate`, `gates`, `all`. Do not reuse the narration or images: the gate blocks them.
