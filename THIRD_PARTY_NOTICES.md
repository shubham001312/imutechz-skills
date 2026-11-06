# Third-party notices

The code and documents in this repo are MIT unless stated here. Bundled third-party material keeps its own licence.

## Fish Video Skill

| Material | Where | Licence |
|---|---|---|
| Sound effects by Kenney (Interface Sounds, Impact Sounds, UI Audio) | `skills/fish-video-skill/sfx/library/` | CC0 ([kenney.nl](https://kenney.nl)); licence files are next to the sounds |
| Meme sound pack: 12 short recordings (sad trombone, dramatic sting, rimshot, applause, laugh, boing, gong, whip, kazoo, party horn, horn, clock) | `skills/fish-video-skill/sfx/library/meme/` | CC0, public domain, CC BY 3.0 and CC BY 4.0, per file. **CC BY needs a credit when a video plays the sound**: authors, sources and SHA-256 hashes are in `LICENSES.md` and `pack.json` in that folder (`render` adds the credit to a project's ledger) |
| Photos in the sample video | `skills/fish-video-skill/examples/why-you-cant-put-it-down/assets/` | Each file's author and licence are in that folder's `credits.json`: CC0, CC BY 4.0 and CC BY-SA 4.0. They are **not** MIT. The CC BY-SA ones, and adaptations of them, stay under CC BY-SA |
| Sample video and its stills | the same `examples` folder | Contains those photos, so the same attribution and share-alike terms apply |

### Installed by the setup, not bundled

Fonts (Inter, Fraunces, JetBrains Mono, Caveat, Noto Sans Devanagari via Fontsource; for themes also Anton, Archivo Black, Courier Prime, DM Sans, DM Serif Display, Fredoka, IBM Plex Mono, Oswald, Playfair Display, Press Start 2P, Righteous, Source Serif 4, Space Grotesk under the SIL OFL 1.1, and Special Elite and Permanent Marker under Apache-2.0; all fetched by `npm install`, none committed), brand icons for thumbnails (`simple-icons`, icon files CC0-1.0, fetched by `npm install`, none committed; the logos are trademarks of their owners, so use them only for brands the video is about), ffmpeg (via `ffmpeg-static`), puppeteer-core, rough.js, yt-dlp, edge-tts. Optional extras the skill can install: rembg, Kokoro (Apache-2.0 code and weights), Chatterbox (MIT; its output carries the PerTh watermark), faster-whisper (MIT), librosa. Each keeps its own licence. Check them for your use, especially ffmpeg builds and any model weights.

### Rights in what you make

Licences for assets you download through the skill are logged per project in `assets/credits.json`. You are responsible for following them, and for the terms of any service you use (ElevenLabs plans, YouTube's terms of service, and so on).

### Ideas from open source

The methods draw on ideas from many open-source projects, listed in `skills/fish-video-skill/references/open-source-field-guide.md`. No code was copied from them.
