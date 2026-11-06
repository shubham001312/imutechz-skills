# Storyboard templates

A storyboard is a list of scenes. Each scene does **one** job. The templates below give working scene orders. Bar counts assume 120 BPM, where one bar is 2 s. They are *starting* counts: the real counts come from the narration (`fishvideo storyboard`).

## Picking a structure

Ask, in this order:
1. **What should the viewer do or believe afterwards?** If they should *understand* something, use an explainer. If they should *try* or *buy* it, use a promo or tour. If they should *notice* something new, use an announcement.
2. **Is there something real to show?** A site or app means at least one `tour` scene, because live proof beats claims. Without one, use the `whiteboard`, `diagram`, `stat` and `terminal` scenes.
3. **How long?** As a rule of thumb:
   - 15 s: hook, one idea, CTA.
   - 30 s: hook plus three beats.
   - 60 s: hook plus five beats.
   - 2–3 min: hook, three chapters of 3–5 scenes each, then the end.
4. **Which platforms?** Build the longest cut first. Shorter cuts *subtract* scenes (`platforms: [youtube]` on the scenes that only YouTube gets). Nothing is re-written per platform except, sometimes, the hook.

## 1. Explainer (60 s ≈ 30 bars)

| # | scene | type | bars | job |
|---|---|---|---|---|
| 1 | hook | kinetic | 2 | the outcome or the tension, ≤ 8 words |
| 2 | title | title | 2–3 | name + one-line promise + chips |
| 3 | idea | bullets / diagram | 3 | the 3 parts, at a glance (`chapter: 01 · What it is`, `wipe`) |
| 4–7 | how-1…how-4 | whiteboard | 3 each | one mechanism per board, with a takeaway line (`chapter: 02 · How it works`) |
| 8 | proof | stat / chart | 2–3 | one sourced number |
| 9 | get | terminal / tour | 3 | how to start |
| 10 | end | end | 2–3 | brand, tagline, links |

## 2. Product tour (45 s ≈ 22 bars)

| # | scene | type | bars | job |
|---|---|---|---|---|
| 1 | hook | kinetic or tour (bare, zoomed) | 2 | "Here's X doing Y" |
| 2 | title | title | 2 | name + promise |
| 3–6 | tour-1…tour-4 | tour | 3–4 each | one page / one feature each, with **one** callout per scene |
| 7 | cta | terminal / bullets | 2 | install, sign up, or the price (sourced) |
| 8 | end | end | 2 | |

Capture plan: one shot per tour scene. Each shot runs about 1.5× the scene length, so the scene can start late and run at `speed: 1.2–1.6`.

## 3. Promo / launch (30 s ≈ 15 bars)

| # | scene | type | bars |
|---|---|---|---|
| 1 | hook | kinetic | 2 |
| 2 | feature | steps (3 cards) | 4 |
| 3 | proof | stat | 2 |
| 4 | see it | tour | 4 |
| 5 | end | end | 3 |

## 4. Listicle ("5 things…", 60 s)

hook (kinetic) → five scenes of 2–3 bars each, all of one type (bullets with a single item, stat, whiteboard) and each with `chapter: "1 / 5"` → recap (bullets) → end.

## 5. Story (90 s)

then (kinetic + image) → the problem (whiteboard) → the turn (quote / kinetic) → now (tour) → proof (chart) → next (bullets) → end.

## 6. Announcement (20–30 s)

kinetic "Introducing …" → title (with a version chip) → 2–3 bullets of what's new → terminal (upgrade command) → end.

## The ImuTechz explainer, as a storyboard (2:40, 80 bars)

```
hook(3) title(4) | 01 process(5) ui(4) | 02 fishTitle(2) fishMmap(3) fishQuant(3) fishInt8(3) fishAvx(3) fishTokens(2) fishKv(3) fishPrefetch(3) models(3)
| 03 agents(6) | 04 look(2) tourHome(4) tourImu(3) tourRd(3) tourDocs(6) tourDir(5) tourTheme(3) | 05 install(4) end(3)
```

- The LinkedIn 4:5 cut (1:12, 36 bars) keeps: hook, title, ui, fishMmap, fishAvx, fishKv, agents, tourHome, tourDocs, install and end.
- The original ImuTechz brief is no longer shipped (it is in git history). For a current long-form reference, see `examples/genai-roadmap-long/`.

## storyboard.yaml anatomy

```yaml
title: Acme in 60 seconds
bpm: 120
hud: {chapter: true, rail: true}      # chapter label top-right, progress rail
grain: true
background: dots                      # dots | plain | wash
custom_scenes: [scenes/custom.js]     # optional project scene code
scenes:
  - id: hook
    type: kinetic
    energy: 1                         # 0 calm … 3 full (music)
    params: {lines: ["Boil water", "~without a flame.~"]}
    say: "Boil water, without a flame."
  - id: how
    type: whiteboard
    chapter: "01 · How it works"
    transition: wipe                  # cut | fade (default) | wipe (chapter cuts)
    platforms: [youtube, linkedin]    # omit = every platform
    params: {tag: How it works, title: "Sun → mirror → pot", flow: [Sun, Mirror, Pot], take: "No fuel, *no smoke*."}
    say:
      - "Sunlight hits a curved mirror."
      - {text: "The mirror focuses it on the pot.", at: 6}    # at = beat, optional
  - id: end
    type: end
    params: {name: Acme, tagline: "Boil with the sun.", links: [acme.dev], cta: "Order at acme.dev"}
    say: "Acme. Boil with the sun."
captures:
  - {id: home, url: "https://acme.dev", auto: {seconds: 8}}
thumbnail: {kicker: "ACME", title: "Boil without fire", accent: fire, badge: "60-second explainer", shot: home}
facts_ok: []                          # numbers you have verified out-of-band (prefer brief.facts)
```

## Scene-writing checklist

- [ ] One idea per scene, and the `say` lines carry exactly that idea.
- [ ] The on-screen words are a subset of the spoken words, or a label for the picture.
- [ ] Headline ≤ 8 words. Bullets ≤ 7 words. Kinetic lines ≤ 6 words.
- [ ] Every number has a source (`source:` on stat/chart; `brief.facts` for numbers in the narration).
- [ ] Tour scenes have exactly one callout at a time.
- [ ] The last scene is `end`.
