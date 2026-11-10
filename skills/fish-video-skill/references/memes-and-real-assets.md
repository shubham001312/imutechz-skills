# Memes, sound clips and real assets

Everything here is a command you can run. The rule behind it: **every asset has a risk tier**, and a project that has not opted in never gets an asset whose licence nobody can verify.

| tier | meaning | examples | what happens |
|---|---|---|---|
| `safe` | public domain, CC0, CC BY / BY-SA, or made by this code | Commons and Internet Archive films and photos with a licence, `sounds synth`, the committed meme sound pack, icons, your own files | downloads freely |
| `platform` | no open licence, shown under the source's own terms | a website screenshot, a logo whose file licence is not open | allowed; QA warns; credits list it separately |
| `unverified` | no licence evidence | Imgflip templates, a clip from Vlipsy, a Myinstants or Memeinstants sound, an Internet Archive item with no licence | **refused** unless the project is `viral` or you pass `--accept-risk`; QA warns; credits list it under "LICENCE NOT VERIFIED" |

The interview asks one optional question, `memes`: `safe` (recommended, and the default when unanswered), `none` or `viral`. It is stored as `memes.policy` in `brief.yaml`. Tools never edit the brief. Viral memes and sounds can get a video claimed, muted or taken down: tell the user before using `viral`.

## Commands (run `fishvideo <tool> <cmd> -h` for every flag)

| command | what it does | source, key | tier |
|---|---|---|---|
| `fishvideo memes sources` | each source, how it is reached and why | none | |
| `fishvideo memes templates <dir> [query] [--gif]` | most-captioned meme templates | Imgflip API, no key for the top list; `IMGFLIP_API_KEY` (paid) searches the full list | unverified |
| `fishvideo memes trending <dir> --region world\|us\|in` | what is being memed now: titles and links, writes `research/memes.md` | Imgflip top list, YouTube search | research only |
| `fishvideo memes films <dir> "<query>" [--region in] [--before 1931] [--unverified]` | public-domain and CC film for reaction cuts | Wikimedia Commons, Internet Archive | safe (archive items with no licence: unverified, hidden unless `--unverified`) |
| `fishvideo assets search <dir> "<query>" --kind photo\|video\|audio\|sfx\|music [--providers a,b]` | candidates with licence, author and preview; provider order for photos: Pexels, Pixabay (keyed), Openverse, Wikimedia Commons, NASA, Library of Congress, Internet Archive (`archive`, key-less: movies and images whose `licenseurl` is CC0, public domain, CC BY or CC BY-SA; NC and ND are dropped, an item with no licence link is `unverified`); `assets source` tries Wikimedia, NASA, the Library of Congress, then the Internet Archive | see the provider | safe or unverified |
| `fishvideo assets get <dir> <id> [--accept-risk]` | download a candidate (size cap, content-type check, http(s) only) | | per candidate |
| `fishvideo memes add <dir> <file-or-url> --title T [--source S --source-url U --license L --author A --id name --accept-risk]` | register a picture or clip you brought | | per claim |
| `fishvideo memes sheet <video> [--every 2]` | a contact sheet with timestamps, to find the moment | local | |
| `fishvideo memes cut <dir> <video> <clip_id> --start S --dur S [--aspect 9:16 --focus x,y]` | a short picture-only clip (sound dropped) for the `meme` or `footage` scene; the licence carries over | local | inherits |
| `fishvideo memes caption <image> <out.png> --top T --bottom B` | classic captions, drawn in the browser so Devanagari shapes correctly | local | |
| `fishvideo memes lint <dir>` | meme scenes: missing credit, repeated gag, memes packed too close; QA runs it | local | |
| `fishvideo sounds synth <dir> [--only a,b] [--all]` | 17 original synthesised cue sounds (airhorn, bassboom, bleep, boing, buzzer, clock, crickets, ding, drumroll, fanfare, heartbeat, rimshot, sadtrombone, scratch, sting, whistledown, whistleup). A type that already has a recording is skipped | made by this code | safe |
| `fishvideo sounds search <dir> "<query>"` | licensed sound effects | Openverse, Wikimedia Commons, Internet Archive, Freesound (`FREESOUND_API_KEY`) | safe |
| `fishvideo sounds add <dir> <file> <cue> [--start S --dur S --level dB --source S --source-url U --license L --accept-risk]` | trim to the hit, fade, normalise, install as cue `<cue>`, set its level, record the source | | per claim |
| `fishvideo sounds list <dir>` / `sounds audition <dir>` | every cue type with its file and level / one montage of all of them with an index | | |
| `fishvideo assets shot <dir> <url...>` | read-only website screenshot, cookie banners hidden by CSS (nothing is clicked) | any site | platform |
| `fishvideo assets github <dir> <owner/repo> [--beat id] [--shot]` | the repo's social card (`assets/github/<owner>-<repo>-card.png`), plus sourced facts for `brief.facts` ("<repo> has 48,213 GitHub stars (as of date)", source = the repo URL; re-running replaces them) and a JSON summary (description, stars, forks, licence, homepage, pushed_at, topics). `--shot` also takes a read-only screenshot of the repo page. `GITHUB_TOKEN` in `.env` is used only to lift the rate limit and is never printed | GitHub public REST API, opengraph.githubassets.com | platform (screenshot of a public page, editorial use; author = the owner) |
| `fishvideo assets terminal <dir> --cmd "<line>" [--cmd ...] [--line "<output>"] [--from-file script.txt] [--out name] [--beat id] [--title zsh] [--scale 2]` | a dark terminal-window card, 1600x1000 (`--scale 2` for 3200x2000), saved to `assets/own/<name>.png`. `--from-file`: lines starting with `$ ` are commands, the rest output. Output text is never invented: any `--line`/output makes the credit `illustrative` ("terminal card made by the skill; output written by the author") and the beat is labelled `illustrative`. Show real output by pasting what the tool printed | made locally (Pillow, DejaVu Sans Mono) | safe |
| `fishvideo assets logo <dir> <brand>` | a brand mark | Simple Icons | safe; trademark note |
| `fishvideo assets icon <dir> <query or set:name>` | an icon from an open-licence set only | Iconify | safe |
| `fishvideo assets emoji <dir> <emoji or name> [--set openmoji\|twemoji]` | an emoji as SVG | OpenMoji CC BY-SA, Twemoji CC BY | safe |

SVGs from the network are untrusted: they are reduced to drawing elements (no scripts, event handlers, foreign content, styles or external references) before they are saved.

## The four sources the user named

- **Imgflip**: automated. `memes templates` uses the official API. Templates are user uploads, mostly of copyrighted images, so they are `unverified`. Regional (Indian) templates need the paid search key.
- **Vlipsy**: not scraped. Its terms forbid scraping and its API is halted; its official route for tools is a hosted MCP server (`claude mcp add --transport http vlipsy https://mcp.vlipsy.com/mcp`, Google sign-in). Download the clip it returns, then `memes add <dir> <file> --title T --source vlipsy --source-url <page>`.
- **Myinstants**: not automated. Its terms allow personal, noncommercial use and forbid scripts that generate searches. It does publish a developer API (footer link, `/api/v1/`; 10 requests a minute anonymous, a token by e-mail), but nothing there lifts those terms, so this tool does not call it. Download in the browser, then `sounds add <dir> <file> <cue> --source myinstants --source-url <page> --accept-risk` (or set `viral`).
- **Memeinstants**: not automated: the site answers automated requests with a bot challenge, so its terms could not even be read. Same manual route.

Giphy (its terms forbid storing copies of its media), Tenor (shut down) and Reddit (access restricted) are not supported.

## The manual route, step by step

1. Open the source page in a browser and download the file.
2. Sound: `fishvideo sounds add <dir> ~/Downloads/x.mp3 airhorn --source myinstants --source-url <page> --start 0.4 --dur 1.5 --level -14 --accept-risk`. It prints where the cue went. Use `airhorn` in a scene's `cues:` or a `meme` scene's `sound:`.
3. Picture or clip: `fishvideo memes add <dir> ~/Downloads/x.gif --title "..." --source vlipsy --source-url <page> --accept-risk`, then `memes cut` for a clip.
4. Run `fishvideo sounds audition <dir>` and listen. The agent cannot hear.

## The `meme` scene

```yaml
- id: wifi
  type: meme
  params:
    clip: gas2                      # or src: assets/meme/x.png
    top: "When the wifi drops"      # "\n" breaks a line; plain text only
    bottom: "mid-demo"
    inset: {src: assets/meme/face.png, pos: br, at: 3}   # optional reaction, at = beat
    punch: 0.14                     # punch-in zoom on beat punch_on (default 2.5)
    sound: rimshot                  # cue type; sound_at = beat
    credit: "Laughing Gas (1914), public domain"
  say: "Then the wifi drops."
```

`fit: contain` (default) shows the whole picture over a blurred copy; `fit: full` fills the frame. Everything is a function of the scene time and sits inside the safe area. See the [scene catalogue](scene-catalogue.md).

## Meme stickers inside a scene

A full-screen `meme` scene is a break. In a fast people or news Short, a reaction works better as a **sticker** inside the beat: the `newsstory` scene takes `fx: [{kind: meme, src: assets/meme/x.png, word: "<spoken word>", x, y, w, top, bottom}]`. The same rules apply (registered file, credit record, policy, no repeated gag), and `memes lint` checks stickers too. Match the meme to the beat's reaction (shock, side-eye, popcorn, applause); use emoji only when the brief says no memes. See [people, news and fact Shorts](news-and-people-shorts.md).

## The committed sound pack

`sfx/library/meme/` holds 12 short licensed recordings (sad trombone, sting, rimshot, applause, laugh, boing, gong, whip, kazoo, party horn, horn, clock): CC0, public domain or CC BY. `pack.json` maps each to a cue type and a default level; `LICENSES.md` has author, licence, source URL and SHA-256. When a render plays a CC BY sound, its credit is added to the project's ledger and appears in the package credits. The famous viral sounds are never committed.

## QA and packaging

`qa` adds `asset licences` (WARN naming every non-safe asset), `meme lint` and `cue sounds` (WARN when a hand-placed cue type has no sample and no built-in synthesis). `package` lists `platform` and `unverified` assets under their own headings in the credits.
