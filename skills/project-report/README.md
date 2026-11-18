# project-report

An agent skill by **ImuTechz** (v1.0.0, MIT). It makes a college project report as a Word file and a PDF, laid out the way students hand them in. It produces:

- a front page with the college name, the centred college logo, the session, the title and a candidate-details box
- optional certificate or acknowledgement pages
- an index with page numbers and a teacher's-signature column
- an introduction with background, objectives and methodology
- the topic sections, a conclusion, learning outcomes and references
- a double-line border on every page

## Install it for an agent

Copy this whole folder into your agent's skills directory, then install the one dependency:

```text
~/.claude/skills/project-report/     # Claude Code
.cursor/skills/project-report/       # Cursor
```

```bash
cd ~/.claude/skills/project-report/scripts && npm install
```

Then ask: *"Make a project report on soil erosion for my Geography class."* The agent asks for the college, student details, guide, topic and any special requirements, then builds and checks the report.

## Use the builder directly

```bash
node scripts/build.js assets/example-config.json report.docx
```

On Windows with Microsoft Word, `scripts/word_pages.ps1` fills in the index page numbers and exports the PDF. The exact commands are in `SKILL.md`, Step 4.

## What's inside

| Path | What it is |
| --- | --- |
| `SKILL.md` | The method: what to ask, getting the logo, content order, build, checks |
| `scripts/build.js` | Builds the .docx from a JSON config (needs the `docx` npm package) |
| `scripts/word_pages.ps1` | Reads each heading's page number in Word and exports the PDF |
| `assets/example-config.json` | A complete config with every option, using placeholder names |
| `assets/placeholder-logo.png` | The stand-in logo used by the example |
| `assets/preview-*.jpg` | Pages of the example report |

## Requirements

- Node 18 or newer.
- For the PDF and index page numbers: Microsoft Word on Windows. LibreOffice can produce the PDF instead, with the page numbers read off the rendered pages.

## A note on honesty

The skill writes draft sections (usually the introduction, conclusion and learning outcomes) and always says which ones it wrote. The student should rewrite them in their own words before submitting. It will not edit metadata or rewrite text to hide that AI helped.

## License

MIT © 2026 ImuTechz. See `LICENSE`. College logos fetched while using the skill belong to their institutions and are not part of this licence.
