# Scene catalogue

## Scene types at a glance

Pick by what the beat has to do. Everything else on this page is detail. A scene type needs its required params, and all others are optional. In tall mode (9:16) every type fills the frame down to the caption band.

| type | required params | best used for | looks weak when |
|---|---|---|---|
| `collage` | `items: [{src, kind: cutout}]`, `title` | a real object with one idea; hooks; paper styles | no real asset; more than 3 labels |
| `split` | `front: {src, title}`, `back: {title}`, `at` | a reveal or turn ("but...") | the two sides say the same thing |
| `cone` | `title` | a dark, quiet turn; one line | long titles; repeated use |
| `coinflip` | `items: [{icon, label}]`, `title` | 2-4 options or ingredients | items need explaining |
| `orbit` | `center`, `title` | one thing surrounded by many | no real centre |
| `neonline` | `steps: [{label, icon}]`, `title` | a loop or a sequence in 3-5 words | labels longer than one word |
| `glowshape` | `title` | an abstract, cinematic idea | nothing to hold on to |
| `tunnel` | `title` | "deeper", repetition, transitions | used as content |
| `ringbloom` | `value` | a value with a many-parts feel | no number |
| `kinetic` | `lines: ["..", ".."]` | hooks and payoffs; 2-6 words a line, `*one accent*` | a full sentence on a line |
| `title` | `title` | an opening card with a real brand | as a hook (too calm) |
| `stat` | `value` (sourced), `label`; `prefix`, `suffix`, `of`, `visual: grid\|ring\|bar\|none` | one striking figure | three in a row; a label over 12 words |
| `chart` | `data: [{label, value}]`, `title`, `source` | 2-6 comparable values | one value (use `stat`) |
| `diagram` | `nodes: [{label, sub}]`, `title`; `morph: true` | a chain of 2-4 steps | over 4 nodes; long subs |
| `whiteboard` | `items` or `flow` | hand-drawn explaining | little to draw |
| `bullets` | `items: [".."]`, `title` | 2-4 short points | over 4 items; sentences |
| `steps` | `items: [{t, d}]`, `title` | how-to, in order | over 4 steps |
| `compare` | `left` and `right: {label, items}`, `title` | before / after, us / them | over 3 rows a side |
| `quote` | `text`, `by` | a real quotation | over 25 words; unattributed |
| `terminal` | `lines: [{cmd} \| {out}]` | developer content | non-developer audience |
| `image` | `src`; `title`, `caption`, `credit`; `treat: none`, `frame: cover\|card` | a real photo that proves the point | a dull photo; no title |
| `roadmap` | `nodes: [{tag, label, src\|glyph}]`, `visits: [{i, word\|t}]` | a recurring map in a long explainer; chapter openers | a short video with few stops |
| `pile` | `cards: [{src, url, x, y, w}]`, `title`, `title_word` | "too many things": real sites burying the viewer | fewer than 3 cards |
| `story` | `src` or `srcs: [{src, word\|at}]`, `kicker`, `lines: [{text, word\|at, size, dim}]`, `motif: none\|date\|stamp\|route\|rings\|dust`, `pan`, `contain` | the photo leads the frame: slow push-in, small text low; the main scene of a story Short | no real photo (use `bold`) |
| `statement` | `lines`, `src` (optional dimmed photo), `floor` | a calm claim; later lines are visible but dimmed from frame 0 | three in a row |
| `cards` | `items: [{tag, t, d, src, word\|at}]`, `cols`, `kicker`, `title` | 3-6 ideas, each lighting on its word; all visible dimmed from frame 0 | over 6 items |
| `flow` | `nodes: [{glyph, label, sub, src, word\|at}]`, `kicker`, `title` | a pipeline of 3-4 boxes joined by glowing arrows | over 4 nodes |
| `site` | `shots: [{src, url, word\|at}]`, `notes`, `kicker`, `title` | a real site in a browser frame with notes beside it (never a thumbnail) | no screenshot to show |
| `bold` | `lines: [{text, word\|at, size, color}]`, `shape: circle\|burst\|bar\|none`, `g` | typographic Shorts: flat colour, one big shape, huge words springing in | long sentences |
| `footage` | `clip` or `frames` | real moving pictures | stock with nothing happening |
| `meme` | `src` or `clip`; `top`, `bottom`, `inset`, `punch`, `sound`, `credit` | a joke beat with a picture or clip and captions: see [memes and real assets](memes-and-real-assets.md) | the gag needs explaining; a picture with no credit |
| `tour` | `shot` (a capture) | software and websites | no clicks to follow |
| `stepcard` | `n`, `title` | a step label inside a tour | outside a tour |
| `end` | `cta`, and `name` or `tagline` | the close; loops back to the hook's hero | long taglines |
| `thumbnail` | `title` (3 words), `accent`; `image` | the storyboard's `thumbnail:` block | over 5 words |

**Good hooks:** `collage` (a real object), `kinetic` (a short claim with one accent), `split` (a reveal), `stat` (a surprising sourced figure), `footage` (real pictures). **Weak hooks:** `title`, `bullets`, `steps`, `diagram`, `chart`, `end`.

Every scene type lives in `scripts/stage/scenes/*.js`. Each one works at 16:9, 1:1, 4:5 and 9:16, because it lays out inside the platform safe area (`c.safe`) with flex boxes and fits its headlines with `L.fit`.

On-screen text supports light markup:
- `*accent*` colours a word with the accent.
- `~serif italic~` sets a word in serif italic.
- `**bold**` makes it bold.
- `\n` breaks the line.

Timing is in seconds of *scene time*. `c.beat` is 0.5 s at 120 BPM, and entrances land on beats.

## The scene contract

```js
window.SCENES.myScene = {
  build(root, c) {            // once per activation: create DOM under root, return state
    const st = {};
    const box = L.H.box(root, c, { center: true });       // flex column inside c.safe
    st.h = L.H.headline(box, c.p.title, c, { lines: 2 });   // kinetic words, fitted
    return st;
  },
  update(st, t, c) {          // PURE function of t (any order, any worker)
    st.h.at(t, c.beat);       // words rise in from beat 1
    L.H.outAll([st.h.node], t, c);
  },
  cues: (c) => [{ lt: c.beat, type: "hit" }],   // SFX cues in scene time
};
```

`c` has these fields:

| field | meaning |
|---|---|
| `W, H` | design size |
| `u` | `min(W,H)/1080`, the type scale |
| `mode` | `land`, `square`, `port` or `tall` |
| `P` | `true` for portrait (`port` or `tall`) |
| `safe {x,y,w,h}` | the layout area, already above any burned-in captions |
| `dur` | scene length |
| `beat, bar, fps` | timing |
| `p` | the scene's params |
| `brand, theme, lang` | from the brief |

### Helpers

- **`L.words(parent, text, cls)`**: words rising out of a mask. Animate with `.at(t, t0)` and `.outAt(t, t1)`.
- **`L.letters`**: letters popping in one by one.
- **`L.typeAt(node, text, t, t0, cps)`**: typed text with a caret.
- **`L.enter(el, t, t0, d, "rise"|"pop"|"left"|"fade"|"blur")`**: one-line entrances.
- **`L.rough(svg, "rectangle"|"circle"|"line"|"path"|"linearPath", args, opts)`**: a rough.js drawable. `.draw(p)` reveals it by stroke-dash and returns the pen tip.
- **`L.pen(svg).at(tip, vis)`**: the marker that follows the tip.
- **`L.Win(parent, {shot, url})`**: a browser window playing a capture. `.layout(x, y, w, maxH)` sizes it, `.at(frame, cam)` shows a frame, and `.map(pagePoint, r)` converts page coordinates.
- **`L.cam(shot, keys, f)`**: camera keyframes, with `{m|f, d, z, x, y}` (marks or frames). If `x` and `y` are omitted the camera follows the smoothed cursor.
- **`L.logo(parent, brand, size)`**: the brand logo file, or a typographic badge when there is none.
- **`L.fit(node, maxPx, minPx, w, h)`**: binary-searches the font size until the text fits.
- **`L.md(text)`**: the markup above, escaped.
- **`L.rng(seed)`**: deterministic random numbers. Use it instead of `Math.random`.

## The library

### `title`
The brand moment.
- Params: `kicker`, `title`, `subtitle`, `chips[]`, `logo` (default `true`).
- Use it once, near the start.
- Cues: swell, hit, tick, pops.

### `kinetic`
Big words that rise in line by line. Hooks, turns of thought, the thesis.
- Params: `lines[]`, `kicker`, `align` (`center` or `left`), `sub`, `size`, `accent`.
- In tall mode or a styled video, each line is fitted to the safe width, words slam in on a spring and kick the camera, and a line lands on its first word when that is spoken. `*accent*` works; with none marked, the last word takes the accent (`accent: false` turns that off).
- Keep each line ≤ 6 words. A `~serif~` line gives contrast.

```yaml
- {id: hook, type: kinetic, params: {lines: ["AI that lives", "~on your machine.~"]}, say: "AI that lives on your machine."}
```

### `bullets`
Numbered points that arrive one per narration beat.
- Params: `kicker`, `title`, `items[]`, `source`.
- 3–5 items, each ≤ 7 words.

### `steps`
Numbered cards: a row in landscape, a column in portrait.
- Params: `kicker`, `title`, `items: [{t, d}]`.

### `stat`
One number counting up, with a label and a **required** source.
- Params: `value`, `prefix`, `suffix`, `decimals`, `label`, `source`, `grouping`, `of`, `visual`.
- In tall mode or a styled video, the number is fitted to the safe width and counts up on a spring, over a visual that fills the room below. `visual`: `grid` (out of 100 for a percentage or with `of`, else one tile per unit up to 200), `ring`, `bar` (filled to `value / of`; without `of` it only sweeps), or `none`. The default is `grid` for a percentage or a whole number up to 200, else `bar`.
- The value must come from `brief.facts` or `research/`.

### `chart`
Animated bars: vertical in landscape, horizontal otherwise.
- Params: `title`, `data: [{label, value}]`, `unit`, `prefix`, `decimals`, `highlight` (a label), `source`, `kind` (`bar` or `hbar`).
- 2–6 bars. Highlight the one that matters (by default, the last one).

### `diagram`
Boxes joined by arrows (rough or clean), 3–5 nodes.
- Params: `title`, `nodes: [{label, sub, hi}]`, `caption`, `style` (`rough` or `clean`).
- Use it for architecture or a pipeline.

`morph: true` on `diagram`: one box re-labels and grows into each next step (`nodes[].label`, `sub`), with the text swap and the growth on springs.

### `whiteboard`
The hand-drawn explainer board: grid paper, a Caveat title, rough.js strokes drawn by a marker pen, and a highlighted takeaway.
- **Fast path:** `flow: [A, B, C]` plus `notes: [...]` gives boxes and arrows. They lay out horizontally in landscape and vertically in portrait.
- **Full control:** `items` in a 1600×700 board space, each timed in beats. Kinds:
  - `rect: [x, y, w, h]`
  - `circle: [cx, cy, d]`
  - `line: [x1, y1, x2, y2]`
  - `arrow: [x1, y1, x2, y2]`
  - `path: "M… C…"`
  - `note: "text"` with `x`, `y`, `size`, and `acc` for the accent colour
  - `cells: {x, y, cols, rows, w, h, gap}`: memory cells lighting up
  - Common keys: `at` (beat), `dur` (beats), `color` (`ink`, `accent` or `muted`), `fill` (`accentSoft`, `accent` or a CSS colour), `seed`.

```yaml
- id: mmap
  type: whiteboard
  params:
    step: 1
    tag: "Inside FISH"
    title: Memory-map the GGUF
    take: "The file is *mapped*, not copied."
    items:
      - {path: "M60 60 L330 60 L400 130 L400 640 L60 640 Z", at: 0.5, dur: 1.4}
      - {note: "model.gguf", x: 98, y: 92, size: 34, at: 1.6, dur: 1}
      - {arrow: [440, 350, 760, 350], at: 4, dur: 0.9}
      - {note: "mmap", x: 540, y: 240, size: 64, acc: true, at: 4.4, dur: 0.8}
      - {rect: [800, 80, 740, 560], at: 2.4, dur: 1.4}
      - {cells: {x: 840, y: 120, cols: 9, rows: 6, w: 62, h: 66, gap: 14}, at: 6, dur: 4.4}
```

**When to use it:** for a *process*, where seeing it built teaches more than seeing it finished.
- Avoid it for lists: use bullets.
- Avoid it for UI: use tour.

### `compare`
Two columns: the old way (dimmed) against the new way (accent border).
- Params: `title`, `left: {label, items}`, `right: {label, items}`.

### `quote`
A large serif quote with attribution.
- Params: `text`, `by`, `role`.
- Real, sourced quotes only.

### `terminal`
Commands typed live, with output and comments.
- Params: `kicker`, `title`, `lines: [{cmd}|{out}|{comment}]`, `chips[]`, `cps`.

### `tour`
A recorded live shot inside a browser frame:
- the camera zooms on `cam` keys or follows the cursor
- the drawn cursor, click ripples and key-combo badges replay what was recorded
- callouts are anchored to page coordinates
- a side panel (landscape) or top panel (portrait) holds the eyebrow, title and bullets

Params: `shot`, `url`, `from` (a frame number or a mark), `speed`, `eyebrow`, `title`, `bullets`, `cam`, `callouts: [{text, m|t0, d, len, page: {x,y} | x,y, align}]`, `full`, `cursor`.

```yaml
- id: docs
  type: tour
  params:
    shot: docs
    url: example.com/docs
    from: index
    speed: 1.0
    eyebrow: Documentation
    title: "23 guides, *one search*."
    cam: [{m: index, z: 1}, {m: ctrlk, d: 24, z: 1.32, x: 720, y: 300}, {m: landed, d: 10, z: 1}]
    callouts:
      - {text: "“streming”, a typo, *still found*", m: type, d: 30, len: 2.6, page: {x: 1060, y: 120}, align: right}
```

### `image`
A still image with a slow push-in.
- Params: `src` (a path relative to the project), `title`, `caption`, `credit`, `fit`, `push`, `pan`, `treat` (`none` turns the treatment off), `frame` (`cover` or `card`), `contrast`.
- In tall mode or a styled video it takes the style's treatment. On a paper ground it is a large halftone card with a shadow. Otherwise the photo covers the frame on a far plane (parallax), graded, with a scrim, a glow frame and a slow Ken Burns.
- Use only images the user owns or provided.

### `end`
The brand close.
- Params: `name`, `tagline`, `links[]`, `cta`, `logo`, `bg`, `loop`, `size`, `lines`.
- In tall mode, or in any styled video, it is the strong close: a huge title fitted to the safe width, a CTA pill, and a textured background from the brief. The hook's hero waits below and grows back to its hook pose over the last 0.85 s, so the last frame leads into the first (`loop: false` removes this, and the film-end fade comes back).
- The hero rests clear of the CTA pill (the title shrinks if it needs the room). The title clears when the hero starts growing; the CTA stays until the last 0.3 s.
- `lines`: a number is the title's line limit; a list is the title's lines. With no `name` and no brand name, the tagline becomes the title. With no hero to return to, the block is centred inside a slowly drawn accent ring. Ink follows the ground on every style.
- A badge appears only with a logo file or an explicit `brand.name`. `brand.name` falls back to the video title, and the timeline's `brand.explicit_name` tells the two apart. `logo: true` forces it.
- Music energy 0 (the outro hit and bell figure).

### `thumbnail`
A static 1280×720 composition (the `thumbnail:` block in the storyboard).
- Params: `kicker`, `title` (2–5 words), `accent` (one word to colour), `badge`, `shot` or `image`.

## Transitions and HUD

- **`transition`** sets how a scene arrives:
  - `fade` (default): a 0.22 s soft cross through the background, with a little blur on the way out.
  - `wipe`: an ink panel with an accent edge sweeps across, centred on the cut. Use it for chapter changes; it gets a whoosh.
  - `cut`: a hard cut.
  - `zoom` (portal): the camera flies into scene A (a real camera z-move plus motion blur over 0.32 s), a 2-frame white flash covers the cut (no wash after it in a styled video), and scene B starts tight and pulls back over 0.75 s on cubic-bezier(.16,1,.3,1). Cues: whoosh (0.42 s before), flash, impact.
  - **No blank frames (styled videos):** a scene holds its content up to the cut unless the transition is `fade`, and entrances run ahead of the clock by `lead` seconds (0.45, 0.6 on the first scene, 0 for tour and footage), converging on real time by 1.2 s, so a scene opens with its subject up. `lead` is a scene field.
  - `flash`: a hard cut under a 2-frame white flash; B settles from 1.06 to 1. Cues: flash, hit.
  - `defocus`: a rack-focus cross-dissolve. B is sharp at once while A blurs to 14 px and fades over it for 0.36 s, so no frame is empty. Cue: whoosh.
  - `flip`: a 3D Y-flip match cut. A turns to 90°, B turns in from -90° (perspective 1400 px). Cue: swish.
  - `flood`: a colour flood. The accent closes over A in a circle for 0.2 s and lifts off B for 0.2 s, power2.inOut. Cue: whoosh.
  - `dip`: a dip cut. A hard cut with the frame darkened 40% for 3 frames. Cue: hit.
  - `iris`: a clip-path circle, 0.15 s shut on A and 0.15 s open on B, over black. Cue: swish.
  - `through`: zoom through a target. A tracks its hero to the centre over 0.6 s, then scales it through the frame in 0.35 s (power3.in, ending at 250% of the frame) and B lands sharp in 0.13 s. A scene names its target with `st.target = {x, y, share}`. Cues: whoosh, impact.
  - `match`: the outgoing hero stays on screen across the cut and flies, scales and turns to its place in the next scene (0.5 s; `params.match_dur` 0.2-1.2 on the incoming scene) while the rest of A dissolves in 0.22 s. Pairing: the same `src`, else an item with `match: true`, else the first hero (different sources cross-fade in flight). Collage items and the end card's hero take part; with no hero on either side it is a plain dissolve. Cues: swish, pop.
  - `world`: the object becomes the world. B starts as an object at 8% over black and scales to full frame in 0.35 s (power3.in). Cue: whoosh.
- **HUD**:
  - `chapter: "02 · Inside FISH"` shows a mono label at the top right (it is hidden on title, end and kinetic scenes unless `hud: true`).
  - A progress rail runs along the bottom edge.
- Grain and vignette are on by default (`grain: false` turns grain off).

## Writing a custom scene (checklist)

- [ ] Put it in `<project>/scenes/custom.js` and list it in `custom_scenes`. Listing any custom scene lets the validator accept types it does not know, so check the spelling of your scene types.
- [ ] Do not reuse a built-in scene name (`pile`, `roadmap`, ...): your file loads last and replaces the built-in for the whole video. `storyboard` warns when it finds this.
- [ ] If a scene reveals items on spoken words, show them DIMMED (opacity about 0.14) from the first frame and light each on its word. Do not start empty: the first word can land seconds in, and the frame sits bare. Built-in scenes already do this or fall back to beat times; there is no shared wrapper, because each scene owns its own reveal.
- [ ] Mark drawn numbers that are not claims (a glyph standing for an embedding) with `glyph: ...` or `decorative: true` on the item, so `research check` skips them.
- [ ] Lay out inside `c.safe`. Size type as `N * c.u`. Fit headlines.
- [ ] Make `update` a pure function of `t`. Use no timers, no `Math.random`, no CSS transitions.
- [ ] Load images through `L.setImg`, which waits for the decode.
- [ ] Return `cues` for every visible event (pop, whoosh, scribble, typing, click).
- [ ] Check it with `fishvideo stills <dir> --scenes` on every platform, then with `qa` (the text lint).

## Looks: collage, studio, neon, footage, screen explainer

The scenes below come from `scenes/collage.js`, `scenes/fx.js`, `scenes/footage.js` and `scenes/capture.js`, with helpers in `looks.js` (textures, halftone, icons, arrows, kinetic type) and `camera.js` (the 3D camera rig). Times are in beats unless the name says seconds. Positions (`x`, `y`, `w`) are fractions of the safe area.

### Cues and density

Every scene emits cues from this vocabulary: `pop`, `tick`, `click`, `swish` (a 150 ms move), `whoosh` (a longer move), `wipe`, `riser {len}` (it ends at `lt`, so `lt` sits on the reveal), `impact`, `boom`, `thump`, `zap`, `flash`, `coin`, `paper`, `ripple`, `typing {len}`, `scribble {len}`, `chime`, `hit`, `swell`. Swishes and whooshes are placed 0.1 s before the motion they belong to.

A scene's explicit `cues: [{lt, type, lvl}]` are added to the ones the scene emits, and QA fails if a cue the density keeps never reaches the render. A `type` can be your own: put samples in `assets/sfx/<type>/` and set its level in `brief.mix.sfx_levels: {<type>: -14}` (default -22 dBFS).

Each cue carries `lvl`: 1 = an entrance (kept by `rich`), 2 = a transition or reveal (kept by `standard`), 3 = a big moment (kept by `minimal`). The density comes from `sfx: {density: rich | standard | minimal}` in the brief or storyboard (a bare string also works), and a scene can override it with `params.sfx`.

### `collage`
Crumpled paper, B&W halftone photo cut-outs with contact shadows, chamfered or octagonal cards with an offset outline, bold Inter 900 labels with hand-drawn curved arrows, and hairline connectors.
- Params: `title`, `title_at` (beat), `title_pos` (`top` or `bottom`), `kicker`, `bg` (`paper`, `studio` or `none`), `items[]`, `labels[]`, `lines[]`.
- `items`: `{src, kind: card|cutout, shape: chamfer|octagon|rect, x, y, w, h|ratio, rot, at, tag, text, fill, halftone (default true), contrast, cell, outline (px, cut-outs), z, small}`. A cut-out is a transparent PNG/SVG that gets a white outline and a drop-shadow contact shadow (offset down-right, 24 px blur). Its opaque bbox is measured on load, so `w` means the visible object, whatever padding the file has.
- Layout: the title is sized first (paper strips in portrait; `title_strip` overrides that). Items then get the room from the title down to the caption band, across the whole frame width, with `y` as a fraction of that room, and they shrink to fit it. In portrait the first item fills 60-85% of the frame width (`small: true` opts out), and only a subject too tall for the room tucks under the title's strips. `layout: free` keeps the old fractions of `c.safe`.
- `labels`: `{text, x, y, align, size, rot, at, on, sync, z, color (a colour or accent), bg, plain, arrow: {to: item index | [x, y], bend, at, inset}}`. `x, y` are wishes: at build time each label is measured against the object masks, the title, the other labels and earlier arrows, and moved to the nearest free space inside `c.safe`. If no spot is free, the subject slides aside to open a column, then shrinks. In portrait a label is a paper sticker of at least 4% of the frame height (`plain: true` removes the sticker). A styled video lands a label on its own word when the narration says it (`on: word` names another word, `sync: false` keeps `at`), so timing survives re-voicing.
- Arrows are hand-drawn curves of 100-300 px from the label's edge to just off the object's edge, bowing away from the object, with a proper head.
- `lines`: `[[i, j]]` or `{a, b, at}`. Each one draws a hairline edge to edge with dot ends.
- Items arrive on a premium spring, labels on a playful one. Title words use the per-word blur reveal. With a style, the subject floats and takes a small nudge whenever a label lands.
- Depth: background -800, items 0 (or `z`), title +120, arrows +150, labels +180.
- Cues: swish (title), thump (first item, lvl 3), paper + pop (other items), pop + scribble (labels), tick (lines).

```yaml
- id: hook
  type: collage
  bars: 3
  params:
    title: "YOUR BRAIN RUNS ON *AUTOPILOT*"
    items:
      - {src: assets/person.svg, kind: cutout, x: 0.5, y: 0.66, w: 0.62, ratio: 1.25, at: 1, outline: 6, z: 40}
      - {src: assets/clock.svg, shape: octagon, x: 0.2, y: 0.42, w: 0.36, ratio: 1, rot: -7, at: 2, tag: CUE, z: -120}
    labels:
      - {text: "the trigger", x: 0.02, y: 0.66, size: 54, at: 3.6, arrow: {to: 1, bend: 0.35}}
    lines: [[0, 1]]
```

### `split`
A card splits down the middle and the halves slide apart (expo-out) to reveal a second layer behind it.
- Params: `front: {src, title, tag, fill, halftone}`, `back: {src, kicker, title, sub, fill}`, `at` (the beat of the split, 3), `dir` (`v` or `h`), `shape` (`chamfer`, `octagon` or `rect`), `spread` (how far the halves part, 0.46 of the card), `bg` (`paper` or `studio`).
- A white tear line draws down the card in the 0.35 s before the split. The back layer resolves from 0.9 with a blur.
- Depth: back layer -90, halves +30.
- Cues: paper, riser (it ends on the split), swish, impact, pop, tick.

```yaml
- {id: split, type: split, bars: 2, params: {at: 2.2, front: {src: assets/phone.svg, title: WILLPOWER, tag: "PLAN A"}, back: {kicker: "PLAN B", title: "*SYSTEMS*", sub: "beat willpower every time."}}}
```

### `cone`
A near-black stage and a spotlight cone from above. The text exists only inside the light (a conic-gradient mask), with dust in the beam and a pool of light on the floor. The light switches on with a flicker. The title is hero type (85% of the safe width), and the cone fits itself to the measured type, with margin for its feather and swing, so no letter is clipped. A darker beam sits behind the type and the accent is lifted so it stays readable. A line holding an accent word waits until that word is spoken.
- Params: `title`, `sub`, `kicker`, `at` (the beat the light comes on, 1), `angle` (degrees, the minimum), `swing` (degrees, 2.5), `x` (the source position; default the centre of the type), `pool`, `size`, `lines`.
- Cues: thump (lvl 3), zap, swell, tick.

```yaml
- {id: close, type: cone, bars: 2, params: {kicker: "Habit Lab", title: "START SMALL.\nSTART *TODAY.*", at: 0.4}}
```

### `coinflip`
The kinetic studio: a radial #F4F4F4 → #D9D9D9 background, title words that slide in with a motion-blur trail, and subtitle words that scale 0.8 → 1 with a 4 px blur fade over 5 frames, staggered 6 frames. 3D coins (rotateY, perspective 1000 px, a shadow ellipse) land one by one on an arc, each with a label.
- Params: `title`, `sub`, `kicker`, `items: [{icon | src | text, label, color, face}]`, `at` (the beat of the first coin, 2), `gap` (beats between coins, 1), `arc` (0-1 sag), `subject` (a cut-out that rises from the bottom), `halftone`, `bg` (`studio` or `dark`).
- Icons: `bell flame gear star check bolt heart clock target user phone chart lock repeat trophy coffee book sun brain spark arrow up play`.
- Cues: swish (title), tick (sub), whoosh (subject), swish (before each coin) and coin (as each one lands).

```yaml
- {id: wins, type: coinflip, bars: 2, params: {title: "STACK TINY *WINS*", sub: "Small enough that you never skip.", at: 1.6, gap: 0.9, items: [{icon: clock, label: "2 min"}, {icon: check, label: Daily}, {icon: trophy, label: Streak}]}}
```

### `orbit`
A ring of glowing spheres orbiting a centre sphere that holds a word, an icon or an image.
- Params: `title`, `sub`, `kicker`, `center: {text | icon | src}`, `n` (7), `items: [{label}]`, `radius` (0.42), `tilt` (0.32), `speed` (turns per second, 0.07), `ball` (px), `bg` (`dark` or `studio`).
- Cues: pop, swell, a pop for each sphere, chime.

```yaml
- {id: orbit, type: orbit, bars: 2, params: {title: "EVERYTHING *CONNECTS*", center: {icon: brain}, items: [{label: Sleep}, {label: Food}, {label: Move}]}}
```

### `neonline`
The neon diagram: #111 with a 24 px grid (#2A2A2A at 35%), dust and a vignette. A glowing white line draws segment by segment (stroke-dashoffset, easeOutCubic). A glow icon pops at each vertex (scale 0 → 1.1 → 1 over 6 frames, with a feGaussianBlur bloom merged under the source). Labels are neon (`text-shadow 0 0 6px accent, 0 0 20px accent 60%`). An electric arc, seeded per frame and displaced by feTurbulence, trails the draw head.
- Params: `title`, `sub`, `kicker`, `steps: [{label, icon, side}]` (an automatic rising zigzag) or `points: [{x, y, label, icon}]` (0-1 of the chart box, with y = 0 at the bottom), `kind` (`zigzag` or `path`), `seg` (seconds per segment, 0.6), `at` (beat, 1.5), `color`, `glow`, `zap`, `baseline`, `node` (icon radius), `label_size`, `sync`, `pulse`.
- In portrait, `steps` become a tall side-to-side zigzag across the safe width, with node radius 92 and labels of 58 px at 1080 wide.
- A vertex lands on its own label word when the narration says it (`sync: false` keeps `at` and `seg`). Once drawn, a pulse keeps running the line and each vertex answers it (`pulse: false` turns this off).
- `follow` (default true in tall mode): the camera pushes along to the active node, one dot rides the whole path and becomes each next node, passed nodes dim, and a closing pull-back shows the whole diagram for at least 0.8 s (the last node moves earlier if it must).
- The camera's `neon` style follows the draw head.
- Cues: swish, pop (first vertex), zap {len} for each segment, pop at each vertex, chime on the last one.

```yaml
- {id: loop, type: neonline, bars: 2, params: {title: "FOUR STEPS, *ON REPEAT*", at: 1.2, steps: [{label: Cue, icon: bell}, {label: Craving, icon: flame}, {label: Routine, icon: repeat}, {label: Reward, icon: star}]}}
```

### `glowshape`
A glowing #F5F5F5 sphere on a starfield that morphs into a box (the border-radius goes from 50% to 14% while it turns and squashes).
- Params: `title`, `sub`, `kicker`, `label`, `morph` (`box` or `none`), `morph_at` (beat, 3), `stars`, `size`.
- Cues: swish, swell, pop, swish + thump (the morph), pop (the label).

```yaml
- {id: idea, type: glowshape, bars: 2, params: {title: "ONE IDEA", label: "becomes a *system*"}}
```

### `tunnel`
About 25 nested squares (each layer x0.86 and +6°), with an expo-out zoom-through, a starfield and a dark core behind the title.
- Params: `title`, `sub`, `kicker`, `layers` (25), `shrink` (0.86), `twist` (6), `fly` (layers flown through, 7), `zoom` (seconds, 1.8), `color`, `accent_every` (5), `reveal` (seconds, 1.5).
- Cues: whoosh, riser (it ends on the reveal), boom, tick.

```yaml
- {id: repeat, type: tunnel, bars: 2, params: {kicker: Then, title: "REPEAT UNTIL IT'S *AUTOMATIC*", reveal: 1.2}}
```

### `ringbloom`
N circles bloom around a ring, each 30 ms after the last, around a centre value. A shockwave ring follows when the last one lands.
- Params: `title`, `sub`, `kicker`, `value`, `label`, `n` (14), `radius` (0.36), `stagger` (seconds, 0.03), `at` (beat, 1), `dot`.
- Cues: swish, swell, tick, chime, ripple.

```yaml
- {id: ring, type: ringbloom, bars: 2, params: {title: "IN 30 DAYS", value: "30", label: "days of reps", n: 15}}
```

### `roadmap`
A serpentine map of stops joined by a glowing line. The camera lands on a stop when its word is spoken, and is clamped so it never looks past the map and shows bare background.
- Params: `nodes`, `visits`, `open_wide` (seconds: open on the whole map, then push in), `pull_word` or `pull_at`, `pull_dur`, `reveal_all`, `kicker`, `cta`, `cta_word`, `cols` (4), `zoom` (1.42), `wide_zoom` (.68), `move` (.8).
- Use it at every chapter of a long video, so the viewer always knows where they are. `visits[].word` is a word in the scene's narration.

```yaml
- {id: step2, type: roadmap, say: "Step two is where you start building.", params: {open_wide: 1.1, nodes: [{tag: STEP 1, label: Basics, glyph: "f(x)"}, {tag: STEP 2, label: Building, src: assets/site.jpg}], visits: [{i: 0, t: 0}, {i: 1, word: building}]}}
```

### `pile`
Real websites land big in the centre one by one, then settle into a pile, and a line lands over them. Each card is full size when it arrives, so no part of the frame waits empty.
- Params: `cards: [{src, url, x, y, w, rot, word|at}]`, `chips`, `chip_every`, `title`, `title_word`, `title_cue` (swell), `title_size`, `hold_last`.

### `footage`
A stock clip played from pre-extracted frames: `build/clips/<clip>/f_00001.jpg`, and so on, at the project fps. Every frame goes through `L.setImg`.
- Params: `clip`, `frames`, `fps`, `from` (1-based), `speed`, `loop` (true), `fit` (`full` or `card`), `treat: [bw, halftone, grain]`, `grade` (`warm`, `cool` or `teal-orange`), `title`, `kicker`, `title_at` (beat, 1), `title_pos` (`bottom`, `top` or `center`), `push` (0.06), `shape` (card).
- `halftone` on footage is a 45° printed dot screen multiplied over the B&W frame, which keeps it cheap per frame.
- Full-bleed footage sits on an overscanned plane, so camera moves never reveal an edge.
- Cues: whoosh, swish + hit (title), pop (kicker).

```yaml
- {id: clip, type: footage, bars: 2, params: {clip: sunset, frames: 48, fps: 30, treat: [bw, halftone, grain], title: "GOLDEN *HOUR*", kicker: Footage}}
- {id: clip2, type: footage, bars: 2, params: {clip: sunset, frames: 48, fit: card, grade: teal-orange, treat: [grain], title: "IN A *CARD*"}}
```

### `tour`: screen explainer additions
These extend the `tour` above (L.Win, L.cam and the capture meta). Desktop-recorder captures with the same layout (`NNNNN.jpg` + `meta.json` with `x, y, d, c, k, s` per frame) work unchanged.
- `frame`:
  - `browser` (default): window chrome.
  - `inset`: no chrome. A 12 px white border and a drop shadow on a brand-coloured background (`bg` overrides it).
  - `none`: the bare picture.
- `fit`:
  - `contain` (default).
  - `cover`: the view fills its box, which makes a portrait crop that pans with the camera. Portrait `inset`/`none` default to `cover`.
- `cursor: glow`: a white arrow at about 1.5x with a soft halo, and glowing click ripples.
- `zoom: auto` or `{z, ease, hold, gap}`: a virtual camera that zooms to the cursor (1.6-2x) over 0.5 s before each cluster of clicks and pulls back after it, or on a scroll jump. It applies when `cam` is not set.
- `spotlight: [{m|t0, d, len, rect: {x,y,w,h} | follow: true, size, pad, r, dim}]`: everything outside a soft-edged rounded cut-out dims to 66%. The cut-out shrinks onto its target and stays inside the recording.
- `highlight: [{m|t0, d, len, rect, kind: marker|underline|box}]`: marks the text being read.
- Cues: click (lvl 2); typing {len} (runs of key presses); keycombo; whoosh; pop (callouts); swish (each auto-zoom move); swell (spotlights); scribble or pop (highlights).

```yaml
- id: demo
  type: tour
  params:
    shot: app
    frame: inset
    cursor: glow
    zoom: {z: 1.8}
    full: true
    spotlight: [{m: task, d: -10, len: 1.2, rect: {x: 280, y: 160, w: 900, h: 60}}]
    highlight: [{m: task, d: 5, len: 1.4, rect: {x: 320, y: 170, w: 300, h: 40}, kind: marker}]
```

### `stepcard`
A "STEP N" card between the steps of a screen explainer. The number slides in with motion blur and the title resolves word by word.
- Params: `n`, `title`, `sub`, `label` ("Step"), `bg` (`ink`, `accent` or `paper`).
- Cues: swish, hit, pop.

```yaml
- {id: step2, type: stepcard, bars: 1, transition: flash, params: {n: 2, title: "Add a new task", bg: accent}}
```

## Captions

`captions.style` in the brief (or the storyboard) chooses how burned-in captions look:
- `karaoke` (default): the boxed line with words lit as they are spoken.
- `pop`: Shorts-style. Group size follows `voice.delivery`: 2-3 words for high energy, 3-5 conversational, 4-6 calm. A group breaks at a sentence end, a gap of 150 ms or more, or the word limit, and a stranded "the" or "of" moves to the next group. It opens at its first word, closes at or after its last, fades for 0.12 s if it has time, then goes hard off. The type is Inter 900, uppercase, auto-fitted from 78 down to 42 px (at most 900 wide in portrait), with a heavy stroke and a shadow. The spoken word is in the accent colour, and each group scale-pops 0.85 → 1 in 4 frames. The band (10% of the height) is reserved: `c.safe` ends above it. Only scenes over moving pictures (footage, tour) get a 40% backing plate, because local contrast is low there; `params.plate: true|false` overrides that.
- `minimal`: small white type with a shadow and no box.
- `none`: no burned-in captions. The caption area is given back to the safe area.

A silent scene can carry on-screen captions with `caption: "text"` (or a list, like `say`). The words are timed at reading speed, and nothing is spoken.

```yaml
# brief.yaml
captions: {burn: true, style: pop}
# storyboard.yaml
- {id: hook, type: collage, caption: "Most of your day runs on autopilot.", params: {...}}
```

## Textures

`texture` in the brief (or the storyboard) sets the global background. Every texture is generated in the page; none is fetched from a CDN.
- `paper`: crumpled paper, a #C8C8C8 → #707070 radial with a 35% vignette. Two seeded feTurbulence fields are lit by feDiffuseLighting from the top-left and rasterised once to a canvas. Faceted planes, creases, speckle and fibres are added on top.
- `grain`: the plain wash with stronger per-frame grain.
- `clean`: the wash with no grain.
- `grid`: a 24 px ink grid.
- `blueprint`: blue with 24 px and 120 px white grids and a vignette.

Grain is a deterministic per-frame tile (seeded), so it is always the same for a given frame. Images can use `L.treat(url, {bw, halftone, contrast, cell, mix, lift})`, a single cached canvas pass after decode, through `L.setImgFx(img, url, fx)`. Cut-outs use `L.cutFilter({outline, color, shadow})`, an outline built from a stack of drop-shadows plus a contact shadow.

```yaml
texture: paper    # paper | grain | clean | grid | blueprint
sfx: {density: standard}     # rich | standard | minimal
```

## Motion rules

Values in `L.EASE`, `L.SPRING` and `L.TIMING` (`scripts/stage/lib.js`). Sources: the published HyperFrames guidance (Apache-2.0) and the analytic spring maths; reimplemented here.

**Spring.** `L.spring(t, {stiffness: 100, mass: 1, damping: 10})` is the analytic damped spring x(t) = 1 - e^(-ζω0 t)(cos(ω1 t) + (ζω0/ω1) sin(ω1 t)), with ω0 = √(k/m), ζ = c/(2√(km)), ω1 = ω0√(1-ζ²). It is deterministic at any fps. Use ζ 0.7-0.85 for premium arrivals (`L.SPRING.premium`) and ζ 0.4-0.6 for playful pops (`L.SPRING.playful`).

**Easing by role.**

| role | ease | `L.EASE` |
|---|---|---|
| arrivals | expo.out, power4.out | `arrive`, `arrive2` |
| camera moves, colour floods | power2.inOut | `camera`, `flood` |
| zoom-throughs, exits | power3.in | `through`, `exit` |
| rotation, progress | linear (only these) | `linear` |

**Timing.**
- Fast moves take 0.3-0.6 s.
- Exits are 40-50% shorter than entrances.
- The next element starts when the previous one is 30-50% done.
- Stagger: letters 1 frame, words 60-120 ms, list items 40-80 ms.
- Reading hold: 0.5 s + 0.3 s per word (`L.readHold(n)`).
- No stretch over 1.2 s without a new visual event.

**Type.**
- Title reveal (`L.revealWords`): per word, blur 6 px → 0 and opacity 0 → 1 in about 0.13 s, 0.067 s apart.
- Hero words fill 60-90% of the width (`L.fitHero`).
- Body type is 4-9% of the frame height.
- Text stays sharp at rest: depth of field applies to non-text planes unless `dof_text` is set.

**Motion blur.** Peaks are 6-12 px at text size and 15-20 px full frame. Whip smears last 0.13-0.3 s and land sharp in about 0.13 s.

**Transitions.** Zoom through a target: track 0.6 s, then scale from 8% to 250% in 0.35 s with a strong ease-in (`through`). Object becomes world (`world`). Colour flood, 0.4 s (`flood`). Dip cut, darken 40% for 3 frames (`dip`). Iris, clip-path circle 0.15 s (`iris`).

**Captions.** Group 2-3 words for high energy, 3-5 conversational, 4-6 calm. Break at a sentence end, a gap of 150 ms or more, or the word limit. A group opens at or before its first word and closes at or after its last. Exit fade 0.12 s, then hard off. Auto-fit from base 78 down to 42 px, max width 900 in portrait. Use a scrim only when contrast is low.

**Layout.** Action-safe is 90% and title-safe is 80%. `fishvideo qa` (`stills.mjs --lint`, `STAGE.lint`) checks:
- errors: text outside the platform safe area, `text-overlap` (free text on free text) and `text-over-item` (a label on an object's opaque pixels; a title on its own paper strips is exempt)
- warnings (`warnings` in `lint.json`): `outside-action-safe`, and `outside-title-safe` for large type

Mark free-standing text with `data-lb` to include it in the overlap checks.

## Character, accent, hook

- **`anchor: {src, corner: tl|tr|bl|br, x, y, w, rot, at}`** (storyboard level, default off): a small cut-out of the recurring object in every scene, with a contact shadow and a slight drift, reacting to the scene's impact, boom, thump and hit cues. `w` is a fraction of the safe width (0.2). It is placed against the scene's finished layout with `L.placeLabel`, keeping off text and objects; it shrinks, and is left out of a scene where nothing is free or where that object is already the hero.
- **`carry: {src, at, x, y, w, rot, corner}`** (scene field) sets or overrides it for one scene, and `carry: false` removes it. `at` is in seconds.
- **`accent: "#hex"`** (scene field) overrides the brand accent for that scene's CSS variables, captions, glows and `flood`. The type system stays fixed.
- **Hook motion** (first scene with a style or `camera`): frame 0 is full, the camera takes a fast spring push and the title slams 1.14 → 1 from t = 0, with an `impact` cue. `params.hook_motion: false` turns this off.

## Camera

Every scene is filmed by one 3D virtual camera. The scene root has a CSS `perspective` (P = 1100 px at u = 1), and the scene is built in a `preserve-3d` world that moves opposite to the camera. `L.layer(el, z)` puts an element on a depth plane. Each plane is pre-scaled by (P - z) / P, so at the rest pose the layout is exactly what the scene laid out, and the lint checks that layout. Any camera move then gives real parallax. Planes at z ≤ -300 are overscanned by 22%, so lateral moves never reveal an edge.

Typical depths:
- background -800
- the subject 0
- labels and arrows +120 to +250

Layers can be set per item: `z:` on collage items and labels, `bg_z`, `title_z` and `ink_z`.

**Scene fields** (on the scene, or in `params`):
- `camera`, one of:
  - a preset: `static`, `drift`, `dolly-in`, `dolly-out`, `push-in`, `orbit-left`, `orbit-right`, `crane-up`, `crane-down`, `push-through`, `whip-left` or `whip-right`. Combine presets with `+`.
  - a style: `paper` (= drift + dolly-in), `studio` (= push-in 1.0 → 1.08 + bob), `glow` (= push-through), `neon` (= crane-up + follow the draw head) or `screen` (= static; the tour's own zoom-to-cursor does the work).
  - keyframes: `[{t | beat | m, x, y, z, rx, ry, rz, fov, focus_z, ease}]`. Values carry forward, and `ease` (`expo-out`, `cubic`, `cubic-in`, `cubic-out`, `back-out` or `linear`) shapes the segment arriving at that key. `m` is a capture mark (in tour scenes).
  - an object: `{preset, amount, keys, follow}`. `amount` scales the presets, and `keys` add on top of them.
- `camera_from: prev`: start from the previous scene's end pose and blend into this scene's move over `camera_blend` seconds (0.9). One move then carries through the cut.
- `camera_shake: 0..1`: handheld micro-motion. It is seeded smooth noise (a sum of sines), about ±4 px and ±0.3° at 1.
- `camera_shake_on: impact`: adds a short decaying kick on the scene's impact, boom, thump and hit cues.
- `dof` (blur per unit of depth, 0.03) and `dof_max` (6 px): depth of field once a key sets `focus_z`. Each plane blurs by |z - focus_z|. Keyframe `focus_z` for a rack focus. Planes holding text (and the arrow ink) stay sharp; `dof_text: true` blurs them too.

**Default style by scene type:**
- `paper`: collage, split
- `studio`: coinflip, orbit
- `neon`: neonline, ringbloom
- `glow`: glowshape, tunnel
- `drift`: cone, footage
- `screen`: tour
- the original scenes (title, kinetic, bullets, stat, chart, diagram, whiteboard, end and the rest): a subtle `drift`, `drift+dolly-in` or `drift+push-in` when `brief.style` is set
- `static`: the original scenes in a legacy brief with no style and no `camera`, so those projects render as before

**Liveliness**: with a style or a `camera`, every scene but `tour` also gets spring micro-pushes on its spoken phrases (alternating, so they stay bounded). Gaps are filled so that no stretch exceeds about 1.1 s without a new visual event.

**Lens**:
- Motion blur follows the camera's speed above 9 px per frame. Fast lateral moves get a directional blur; z moves get a soft blur.
- The vignette tightens as the camera pushes in.
- `zoom` transitions are real camera z-moves into scene A and out of scene B.

**Cues**: a fast camera move gets a `whoosh` (or a `swish` if it lasts under 0.3 s) 0.1 s before it starts. `push-through` lands an `impact` on arrival.

**Determinism**: the pose is a pure function of (scene, t), with no timers. Fonts used by the stage are preloaded, so the first layout matches every later one.

```yaml
- id: hook
  type: collage
  camera: {preset: drift+dolly-in+orbit-right, amount: 0.55}
- id: split
  type: split
  transition: zoom
  camera_shake: 0.35
  camera_shake_on: impact
  camera:                       # rack focus: the front card, then the layer behind it
    preset: drift
    keys: [{t: 0, focus_z: 30}, {t: 1.0, focus_z: 30}, {t: 1.6, focus_z: -90, ease: cubic}]
- id: repeat
  type: tunnel                  # glow = push-through: the camera flies through at the end
- id: close
  type: cone
  camera_from: prev             # starts inside the push-through and pulls back into the spotlight
  camera_blend: 1.2
- id: whip
  type: coinflip
  camera: whip-left+push-in
- id: keyed
  type: neonline
  camera: [{t: 0, z: 0, ry: -4}, {t: 2, z: 90, ry: 4, ease: expo-out}, {at: end, y: -40}]
```

In a custom scene, call `L.layer(el, z)` after building `el` under the scene root. Set `cam: "paper"` (or any style or preset) on the scene definition to give it a default move, and set `st.camHint = {x, y}` (stage px) in `update` to give the `follow` styles a target.


## Theme-aware scenes

`story`, `statement`, `cards`, `flow`, `site`, `bold` and `roadmap` read the theme (`brief.theme`): colours, the display font, kicker style, card style, radius, shadow, caps and motion speed. They show dimmed content from the first frame (`L.T.dim`), so no frame starts empty. Reveals land on `word` (a spoken word), else `at` (seconds), else are spread evenly. Do not name a project scene after a built-in one; `storyboard` warns.
