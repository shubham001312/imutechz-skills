---
name: project-report
description: Use when a student asks for a college or university project report, project file, assignment file or "project PDF", or wants an existing PDF or notes turned into one. Produces a Word file plus PDF with a front page (college name, centred college logo, session, title, candidate-details box), optional certificate or acknowledgement pages, an index with page numbers and a teacher's-signature column, an introduction (background, objectives, methodology), the topic sections, a conclusion, learning outcomes and references, with a border on every page. Not for theses with a university-mandated template, slide decks, or disguising AI-written work.
version: 1.0.0
license: MIT
author: ImuTechz
compatibility: Node 18+ (the docx npm package, installed by the setup step). Microsoft Word on Windows for the PDF export and index page numbers; LibreOffice works for the PDF, with page numbers read off the rendered pages instead.
---

# Project report

A college project report the way students hand them in: plain academic Word styling, a proper front page, an index the teacher signs, and a PDF exported from Word. Times New Roman 12 pt, 1.5 line spacing, justified text, numbered headings and a double-line border on every page.

Done means two files in the user's folder, `<Name>_Project.docx` and `<Name>_Project.pdf`, where every page has been looked at and the index page numbers match the real pages.

## Files

- `scripts/build.js`: builds the .docx from a JSON config
- `scripts/word_pages.ps1`: opens the .docx in Word, writes each Heading 1's page number for the index, and exports the PDF
- `assets/example-config.json`: a complete config with every option. Read it before writing a new one.
- `assets/placeholder-logo.png`: the logo used by the example. Never put it in a real report.

**Setup, once:** run `npm install` inside `scripts/`.

## Step 1: Ask for the details

Ask in one message, or use your question tool. Skip anything the user already gave.

1. **College or university:** its name, town or state, and the **department**
2. **Student details:** name, semester, session, plus anything else for the front page (roll no., registration no., course)
3. **Guided by:** the teacher's name, used on the front page and under the guide's signature line
4. **Topic or title**, and any **source material** (a PDF, notes or a doc in the folder)
5. **Special requirements**, for example:
   - certificate, acknowledgement or declaration pages
   - a page count or word limit
   - font, paper size or border style
   - extra sections such as maps, tables or a case study
   - extra signature lines, such as the Head of Department

## Step 2: Get the college logo

1. Look in `logos/` next to this file (logos saved on earlier runs), then in the user's folder and Downloads.
2. Otherwise search Wikimedia Commons, then fetch an 800 px PNG of the right file:
   ```bash
   curl -s -A "report-builder/1.0" "https://commons.wikimedia.org/w/api.php?action=query&list=search&srnamespace=6&srsearch=<College>%20logo&format=json&srlimit=10"
   curl -s -A "report-builder/1.0" "https://commons.wikimedia.org/w/api.php?action=query&titles=File:<exact title>&prop=imageinfo&iiprop=url&iiurlwidth=800&format=json"
   ```
   The second call returns a `thumburl`. Download it, then **open the image and check it is the right college's logo**.
3. If nothing reliable turns up, ask the user to put the logo file in the folder. Never draw or invent a college's logo.

When a logo is confirmed, save a copy as `logos/<college>.png` for next time. Set `logoAspect` in the config to the image's height ÷ width so it isn't stretched.

## Step 3: Write the content

The `body` follows this order. Number the headings, but leave `References` unnumbered.

1. **Introduction**, with three sub-headings:
   - `1.1 Background`
   - `1.2 Objectives of the Project` (bullets)
   - `1.3 Methodology` (primary or secondary data, and where it came from)
2. **Topic sections**, from the source material when there is some. Keep facts, figures and citations exact. Never invent statistics or references.
3. **Conclusion**
4. **Learning Outcomes:** "After completing this project, I was able to:" followed by bullets
5. **References:** only real sources the content actually used

Block types in `body`:
- `{"h1": ...}` and `{"h2": ...}` for headings
- `{"p": ...}` for a paragraph
- `{"bullets": [...]}` and `{"refs": [...]}`
- `{"pageBreak": true}`

Inside text, write `**bold**` and `*italic*`. The index is built from the `h1` headings, so don't list sections anywhere else.

Optional pages such as a certificate or acknowledgement go in `frontPages`. They appear between the front page and the index. `signature` is optional.

Other config keys:
- `font` and `fontSize`
- `paper`: `"A4"` or `"Letter"`
- `border`: `"double"`, `"single"`, `"thick"` or `"none"`
- `reportLabel`: the line above the title, default "A Project Report on"
- `detailsHeading`: the heading of the details box, default "CANDIDATE DETAILS"
- `subtitle`
- `bodyTitle`: set it to `false` to hide the title at the top of page 1
- `guideLine`: the line under the guide's name

Write the config to a temporary folder. Give the logo path relative to the config file.

## Step 4: Build, number the index, export

Run these in PowerShell. `$K` is this skill's `scripts` folder, `$T` the temporary folder and `$P` the user's folder.

```powershell
node "$K\build.js" "$T\config.json" "$T\pass1.docx"                                 # index page numbers blank
& "$K\word_pages.ps1" -Src "$T\pass1.docx" -PagesOut "$T\pages.json"               # read the real page numbers
node "$K\build.js" "$T\config.json" "$P\<Name>_Project.docx" "$T\pages.json"        # index filled in
& "$K\word_pages.ps1" -Src "$P\<Name>_Project.docx" -Pdf "$P\<Name>_Project.pdf"    # export the PDF
```

Pass file paths as arguments, never JSON strings: Windows PowerShell 5 strips the quotes from them.

**Without Word:** convert with `soffice --headless --convert-to pdf`. Then read each heading's page off the rendered pages, write `pages.json` as `{"Introduction": 1, ...}`, and rebuild.

## Step 5: Check and report

1. **Open the PDF and look at every page.** Check that:
   - the front page fits on one page
   - the logo is centred and not distorted
   - the index numbers match the real pages
   - no heading is left alone at the bottom of a page
2. Fix anything wrong and rebuild.
3. Tell the user where both files are, and list the pages.
4. Say plainly which sections you wrote yourself, usually the Introduction, Conclusion and Learning Outcomes. They are drafts. The student should rewrite them in their own words, and check that the first-person learning outcomes are true for them, before handing the report in.
5. If the user edits the .docx and the page flow changes, the index numbers are stale. Offer to re-run Step 4.

## Hard rules

- Never invent facts, figures, references or a college logo.
- Never edit document metadata or reword text to hide that AI helped. If asked to, decline and offer help with rewriting instead.
- Personal details (names, roll numbers) stay in the user's files. Never put them in shared examples or logs.
