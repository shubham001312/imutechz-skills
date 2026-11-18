// Builds a college project report (.docx) from a JSON config.
// Usage: node build.js <config.json> <out.docx> [pages.json]
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, ImageRun,
  Footer, PageNumber, Table, TableRow, TableCell, WidthType, BorderStyle,
  ShadingType, VerticalAlign, TabStopType, PageBorderDisplay, PageBorderOffsetFrom,
  PageBorderZOrder, NumberFormat, LevelFormat, PageBreak,
} = require('docx');

const [, , cfgPath, out, pagesPath] = process.argv;
const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8').replace(/^﻿/, ''));
const pages = pagesPath && fs.existsSync(pagesPath)
  ? JSON.parse(fs.readFileSync(pagesPath, 'utf8').replace(/^﻿/, '')) : {};
const base = path.dirname(path.resolve(cfgPath));

const FONT = cfg.font || 'Times New Roman';
const BODY = (cfg.fontSize || 12) * 2;
const LETTER = (cfg.paper || 'A4').toLowerCase() === 'letter';
const PAGE_W = LETTER ? 12240 : 11906, PAGE_H = LETTER ? 15840 : 16838;
const TEXT_W = PAGE_W - 2880;

// ---------- inline markup: **bold**, *italic* ----------
function inline(text, o = {}) {
  const runs = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) runs.push(new TextRun({ text: text.slice(last, m.index), ...o }));
    const t = m[0];
    if (t.startsWith('**')) runs.push(new TextRun({ text: t.slice(2, -2), bold: true, ...o }));
    else runs.push(new TextRun({ text: t.slice(1, -1), italics: true, ...o }));
    last = m.index + t.length;
  }
  if (last < text.length) runs.push(new TextRun({ text: text.slice(last), ...o }));
  return runs;
}
const run = (text, o = {}) => new TextRun({ text, ...o });
const centre = (children, after = 0, before = 0) =>
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before, after }, children });
const para = t => new Paragraph({
  alignment: AlignmentType.JUSTIFIED, spacing: { after: 160, line: 360 }, children: inline(t),
});
const bullet = t => new Paragraph({
  numbering: { reference: 'bullets', level: 0 }, alignment: AlignmentType.JUSTIFIED,
  spacing: { after: 100, line: 340 }, children: inline(t),
});
const ref = t => new Paragraph({
  indent: { left: 720, hanging: 720 }, spacing: { after: 120, line: 276 }, children: inline(t),
});

// Content blocks: {h1}, {h2}, {p}, {bullets:[...]}, {refs:[...]}, {pageBreak:true}
function blocks(list) {
  const outp = [];
  for (const b of list) {
    if (b.h1) outp.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [run(b.h1)] }));
    else if (b.h2) outp.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [run(b.h2)] }));
    else if (b.p) outp.push(para(b.p));
    else if (b.bullets) b.bullets.forEach(t => outp.push(bullet(t)));
    else if (b.refs) b.refs.forEach(t => outp.push(ref(t)));
    else if (b.pageBreak) outp.push(new Paragraph({ children: [new PageBreak()] }));
  }
  return outp;
}

// ---------- tables ----------
const line = { style: BorderStyle.SINGLE, size: 6, color: '000000' };
const cellBorders = { top: line, bottom: line, left: line, right: line };
function cell(text, width, o = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA }, borders: cellBorders,
    verticalAlign: VerticalAlign.CENTER, columnSpan: o.span,
    shading: o.shade ? { type: ShadingType.CLEAR, color: 'auto', fill: 'D9D9D9' } : undefined,
    margins: { top: 100, bottom: 100, left: 140, right: 140 },
    children: [new Paragraph({ alignment: o.align || AlignmentType.LEFT,
      children: [run(text, { bold: !!o.bold })] })],
  });
}

// ---------- page setup ----------
const borderStyles = { double: BorderStyle.DOUBLE, single: BorderStyle.SINGLE, thick: BorderStyle.THICK, none: null };
const bStyle = borderStyles[cfg.border || 'double'];
const pb = { style: bStyle, size: 6, color: '000000', space: 24 };
const pageProps = (extra = {}) => ({
  page: {
    size: { width: PAGE_W, height: PAGE_H },
    margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 },
    ...(bStyle ? { borders: {
      pageBorders: { display: PageBorderDisplay.ALL_PAGES, offsetFrom: PageBorderOffsetFrom.PAGE, zOrder: PageBorderZOrder.FRONT },
      pageBorderTop: pb, pageBorderBottom: pb, pageBorderLeft: pb, pageBorderRight: pb,
    } } : {}),
    ...extra,
  },
});
const emptyFooter = () => new Footer({ children: [new Paragraph({ children: [] })] });
const sigBlock = (title, name, extraLine) => [
  new Paragraph({ spacing: { before: 1400 }, children: [] }),
  new Paragraph({ tabStops: [{ type: TabStopType.RIGHT, position: TEXT_W }],
    children: [run('Date: ____________'), run('\t____________________________')] }),
  ...[[title, true], name ? [`(${name})`] : null, extraLine ? [extraLine] : null]
    .filter(Boolean).map(([t, b]) => new Paragraph({
      tabStops: [{ type: TabStopType.CENTER, position: TEXT_W - 1430 }],
      children: [run('\t' + t, { bold: !!b })] })),
];

// ---------- cover ----------
const c = cfg.college;
const cover = [];
cover.push(centre([run(c.name, { bold: true, size: c.name.length > 30 ? 36 : 48 })], 60));
if (c.location) cover.push(centre([run(c.location, { size: 26 })], 240));
if (c.department) cover.push(centre([run(c.department.toUpperCase(), { bold: true, size: 30 })], 480));
if (cfg.logo) {
  const file = path.resolve(base, cfg.logo);
  const ext = path.extname(file).slice(1).toLowerCase().replace('jpeg', 'jpg');
  const w = cfg.logoWidth || 180;
  const h = Math.round(w * (cfg.logoAspect || 1)); // height / width
  cover.push(centre([new ImageRun({ type: ext, data: fs.readFileSync(file), transformation: { width: w, height: h } })], 200));
}
if (cfg.session) cover.push(centre([run(`Session: ${cfg.session}`, { bold: true, size: 26 })], 600));
cover.push(centre([run(cfg.reportLabel || 'A Project Report on', { italics: true, size: 26 })], 160));
(Array.isArray(cfg.title) ? cfg.title : [cfg.title]).forEach((t, i, a) =>
  cover.push(centre([run(t, { bold: true, size: 32 })], i === a.length - 1 ? 900 : 0)));
const CW = [2600, 3900];
cover.push(new Table({
  alignment: AlignmentType.CENTER, width: { size: CW[0] + CW[1], type: WidthType.DXA }, columnWidths: CW,
  rows: [
    new TableRow({ children: [cell(cfg.detailsHeading || 'CANDIDATE DETAILS', CW[0] + CW[1],
      { span: 2, bold: true, shade: true, align: AlignmentType.CENTER })] }),
    ...cfg.student.map(([k, v]) => new TableRow({ children: [cell(k, CW[0], { bold: true }), cell(v, CW[1])] })),
  ],
}));

// ---------- optional front pages (certificate, acknowledgement ...) ----------
const frontSections = (cfg.frontPages || []).map(fp => ({
  properties: pageProps(), footers: { default: emptyFooter() },
  children: [
    centre([run(fp.title.toUpperCase(), { bold: true, size: 32 })], 480),
    ...blocks(fp.blocks || []),
    ...(fp.signature ? sigBlock(fp.signature.title, fp.signature.name, fp.signature.line) : []),
  ],
}));

// ---------- index (built from h1 headings in body) ----------
const headings = cfg.body.filter(b => b.h1).map(b => b.h1);
const strip = h => h.replace(/^\d+\.\s*/, '');
const IW = [900, 4400, 1100, TEXT_W - 6400];
const index = [
  centre([run(cfg.indexTitle || 'INDEX', { bold: true, size: 32 })], 360),
  new Table({
    width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: IW,
    rows: [
      new TableRow({ tableHeader: true, children: ['Sl. No.', 'Contents', 'Page No.', "Teacher's Signature"]
        .map((t, i) => cell(t, IW[i], { bold: true, shade: true, align: AlignmentType.CENTER })) }),
      ...headings.map((h, i) => new TableRow({
        height: { value: 620, rule: 'atLeast' },
        children: [
          cell(String(i + 1), IW[0], { align: AlignmentType.CENTER }),
          cell(strip(h), IW[1]),
          cell(String(pages[strip(h)] || ''), IW[2], { align: AlignmentType.CENTER }),
          cell('', IW[3]),
        ],
      })),
    ],
  }),
  ...(cfg.guide ? sigBlock('Signature of the Guide', cfg.guide, cfg.guideLine) : []),
];

// ---------- body ----------
const body = [];
if (cfg.bodyTitle !== false) {
  body.push(new Paragraph({ style: 'Title', children: [run(cfg.bodyTitle || [].concat(cfg.title).join(' '))] }));
  if (cfg.subtitle) body.push(centre([run(cfg.subtitle)], 360));
}
body.push(...blocks(cfg.body));

const doc = new Document({
  styles: {
    default: { document: { run: { font: FONT, size: BODY } } },
    paragraphStyles: [
      { id: 'Title', name: 'Title', basedOn: 'Normal', next: 'Normal', run: { font: FONT, size: 32, bold: true },
        paragraph: { alignment: AlignmentType.CENTER, spacing: { before: 0, after: 120 }, keepNext: true } },
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: BODY + 4, bold: true },
        paragraph: { spacing: { before: 240, after: 120 }, keepNext: true, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: BODY + 2, bold: true, italics: true },
        paragraph: { spacing: { before: 160, after: 80 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•',
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] }] },
  sections: [
    { properties: pageProps(), footers: { default: emptyFooter() }, children: cover },
    ...frontSections,
    { properties: pageProps(), footers: { default: emptyFooter() }, children: index },
    {
      properties: pageProps({ pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } }),
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: [PageNumber.CURRENT] })] })] }) },
      children: body,
    },
  ],
});

Packer.toBuffer(doc).then(b => fs.writeFileSync(out, b));
