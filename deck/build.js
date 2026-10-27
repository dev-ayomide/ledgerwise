// Builds deck/Ledgerwise.pptx. Screenshots in video/shots are used when present.
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const INK = "0F1B2D", PANEL = "16263D", EMERALD = "0B8F6A", MINT = "3ECF9E", AMBER = "E8A317", PAPER = "F5F7FA", WHITE = "FFFFFF", MUTED = "5A6472", RED = "C0392B";
const HEAD = "Cambria", BODY = "Calibri";
const SHOTS = path.join(__dirname, "..", "video", "shots");
const shot = (n) => { const f = path.join(SHOTS, n); return fs.existsSync(f) ? f : null; };

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625
pres.title = "Ledgerwise";
pres.author = "Ledgerwise";

function title(s, text, dark) {
  s.addText(text, { x: 0.5, y: 0.35, w: 9, h: 0.8, fontFace: HEAD, fontSize: 32, bold: true, color: dark ? WHITE : INK, margin: 0, isTextBox: true });
}
function footer(s, n, dark) {
  s.addText("Ledgerwise · Open Agent Hackathon 2026 · Track 02", { x: 0.5, y: 5.25, w: 7, h: 0.25, fontFace: BODY, fontSize: 10, color: dark ? "9AA5B4" : MUTED, margin: 0, isTextBox: true });
  s.addText(String(n), { x: 9.0, y: 5.25, w: 0.5, h: 0.25, fontFace: BODY, fontSize: 10, color: dark ? "9AA5B4" : MUTED, align: "right", margin: 0, isTextBox: true });
}
function card(s, x, y, w, h, head, body, opts = {}) {
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.08, fill: { color: opts.fill || WHITE }, line: { color: "DDE1E7", width: 0.75 }, shadow: { type: "outer", color: "000000", opacity: 0.12, blur: 6, offset: 2, angle: 90 } });
  s.addText(head, { x: x + 0.2, y: y + 0.15, w: w - 0.4, h: 0.4, fontFace: HEAD, fontSize: 16, bold: true, color: opts.headColor || EMERALD, margin: 0, isTextBox: true });
  s.addText(body, { x: x + 0.2, y: y + 0.6, w: w - 0.4, h: h - 0.75, fontFace: BODY, fontSize: 14, color: opts.color || INK, margin: 0, valign: "top", fit: "shrink", isTextBox: true });
}

// 1 Title
let s = pres.addSlide(); s.background = { color: INK };
s.addText("Ledgerwise", { x: 0.7, y: 1.4, w: 8.6, h: 1.0, fontFace: HEAD, fontSize: 60, bold: true, color: WHITE, margin: 0, isTextBox: true });
s.addText("The agent that explains why the money does not add up", { x: 0.7, y: 2.5, w: 8.2, h: 0.9, fontFace: BODY, fontSize: 24, color: MINT, margin: 0, isTextBox: true });
s.addText("Track 02: The Agent That Can Explain Why\nBuilt on Zetaris, NVIDIA Nemotron and Meterless", { x: 0.7, y: 3.8, w: 8, h: 0.8, fontFace: BODY, fontSize: 16, color: "C9D3E0", margin: 0, isTextBox: true });
s.addNotes("Ledgerwise investigates payment settlement gaps and explains them with evidence.");

// 2 Problem
s = pres.addSlide(); s.background = { color: PAPER };
title(s, "Settlements are short, and nobody can say why");
s.addText("NGN 4,200,000", { x: 0.5, y: 1.4, w: 4.6, h: 1.1, fontFace: HEAD, fontSize: 48, bold: true, color: RED, margin: 0, isTextBox: true });
s.addText("short on one day's settlement", { x: 0.5, y: 2.5, w: 4.6, h: 0.4, fontFace: BODY, fontSize: 16, color: MUTED, margin: 0, isTextBox: true });
s.addText([
  { text: "The processor, the ledger, the bank file and support tickets each tell a different story", options: { bullet: true, breakLine: true } },
  { text: "Reconciliation analysts spend hours in spreadsheets, and the money stays missing", options: { bullet: true, breakLine: true } },
  { text: "Causes stack: a duplicate webhook, a timezone cutoff and a fee mismatch can all hit the same day", options: { bullet: true } },
], { x: 5.2, y: 1.4, w: 4.3, h: 3.2, fontFace: BODY, fontSize: 16, color: INK, paraSpaceAfter: 10, valign: "top", margin: 0, isTextBox: true });
footer(s, 2);

// 3 User
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "Who it is for");
card(s, 0.5, 1.4, 4.3, 3.4, "The user", "A finance operations or reconciliation analyst at a payments company or fintech.\n\nSecondary: the engineer on call for a payment incident.");
card(s, 5.2, 1.4, 4.3, 3.4, "The job", "Turn \"the numbers do not match\" into \"here is exactly why, here is the proof, here is what to do\".\n\nStarting with Nigerian payment rails: NIP transfers, WAT business days, a 20:00 UTC bank cutoff.");
footer(s, 3);

// 4 Solution flow
s = pres.addSlide(); s.background = { color: PAPER };
title(s, "How the investigation works");
const steps = [["Ask", "One question, one value date"], ["Plan", "Checks ordered by the sign of the gap"], ["Query", "Federated SQL across four sources"], ["Disprove", "A second query tries to prove each cause wrong"], ["Report", "Amounts in code, evidence for every claim"]];
steps.forEach((st, i) => {
  const x = 0.5 + i * 1.82;
  s.addShape(pres.ShapeType.ellipse, { x: x + 0.55, y: 1.5, w: 0.6, h: 0.6, fill: { color: EMERALD }, line: { color: EMERALD } });
  s.addText(String(i + 1), { x: x + 0.55, y: 1.5, w: 0.6, h: 0.6, fontFace: HEAD, fontSize: 20, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0, isTextBox: true });
  s.addText(st[0], { x, y: 2.25, w: 1.7, h: 0.4, fontFace: HEAD, fontSize: 18, bold: true, color: INK, align: "center", margin: 0, isTextBox: true });
  s.addText(st[1], { x, y: 2.7, w: 1.7, h: 1.2, fontFace: BODY, fontSize: 14, color: MUTED, align: "center", valign: "top", margin: 0, isTextBox: true });
});
s.addText("The agent only reads. Actions are drafts that a person approves. Nothing is executed.", { x: 0.5, y: 4.2, w: 9, h: 0.5, fontFace: BODY, fontSize: 16, bold: true, color: EMERALD, margin: 0, isTextBox: true });
footer(s, 4);

// 5 Architecture
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "Architecture");
const box = (x, y, w, h, t, fill, col) => { s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.06, fill: { color: fill }, line: { color: fill } }); s.addText(t, { x, y, w, h, fontFace: BODY, fontSize: 13, bold: true, color: col || WHITE, align: "center", valign: "middle", margin: 0.05, isTextBox: true }); };
box(0.5, 1.5, 1.6, 0.8, "Browser UI\nplain HTML/JS", INK);
box(2.5, 1.5, 1.6, 0.8, "FastAPI\nSSE stream", INK);
box(4.5, 1.5, 1.8, 0.8, "Investigator\ndetect, disprove, reconcile", EMERALD);
box(6.7, 1.5, 1.4, 0.8, "SQL guard", AMBER, INK);
box(8.4, 1.5, 1.1, 0.8, "Zetaris", EMERALD);
[2.1, 4.1, 6.3, 8.1].forEach((x) => s.addShape(pres.ShapeType.line, { x, y: 1.9, w: 0.4, h: 0, line: { color: MUTED, width: 1.5, endArrowType: "triangle" } }));
box(5.6, 3.1, 1.9, 0.8, "Nemotron Ultra\nsummary", "76B900");
box(7.7, 3.1, 1.8, 0.8, "Meterless\nsecond check", INK);
s.addShape(pres.ShapeType.line, { x: 5.4, y: 2.3, w: 0.5, h: 0.8, line: { color: MUTED, width: 1.5, endArrowType: "triangle" } });
s.addText("Zetaris federates three physical systems:", { x: 0.5, y: 2.9, w: 4.8, h: 0.35, fontFace: BODY, fontSize: 14, bold: true, color: INK, margin: 0, isTextBox: true });
s.addText([
  { text: "Processor DB (Postgres): transactions, ledger, merchants", options: { bullet: true, breakLine: true } },
  { text: "Webhook log and support tickets (Postgres)", options: { bullet: true, breakLine: true } },
  { text: "Bank settlement files (Parquet)", options: { bullet: true } },
], { x: 0.5, y: 3.3, w: 4.8, h: 1.3, fontFace: BODY, fontSize: 13, color: INK, valign: "top", margin: 0, isTextBox: true });
s.addText("Amounts are integer kobo end to end. Models never produce a number.", { x: 5.6, y: 4.2, w: 3.9, h: 0.6, fontFace: BODY, fontSize: 13, italic: true, color: MUTED, margin: 0, isTextBox: true });
footer(s, 5);

// 6 Stack
s = pres.addSlide(); s.background = { color: PAPER };
title(s, "Stack");
const rows = [["Layer", "What we use"], ["Data access", "Zetaris Lightning SQL (REST), Spark SQL"], ["Sources", "Postgres x2, Parquet files; synthetic data from a seeded generator"], ["Backend", "Python, FastAPI, SSE, sqlglot SQL guard, Pydantic"], ["Models", "NVIDIA Nemotron Ultra (summary), Meterless Nightshift (check)"], ["Frontend", "Plain HTML, CSS, JS. No build step"], ["Quality", "38 tests, 21-scenario eval with a held-out set"]];
s.addTable(rows.map((r, i) => r.map((c) => ({ text: c, options: { bold: i === 0, color: i === 0 ? WHITE : INK, fill: { color: i === 0 ? INK : (i % 2 ? WHITE : "EEF1F5") }, fontFace: BODY, fontSize: 14 } }))), { x: 0.5, y: 1.4, w: 9, colW: [2.0, 7.0], rowH: 0.45, border: { type: "solid", color: "DDE1E7", pt: 0.75 }, margin: 0.08 });
footer(s, 6);

// 7 Zetaris
s = pres.addSlide(); s.background = { color: INK };
title(s, "How Zetaris was used", true);
s.addText([
  { text: "Every query goes through Zetaris Lightning SQL", options: { bullet: true, breakLine: true } },
  { text: "Postgres sources via CREATE DATASOURCE, bank Parquet via CREATE LIGHTNING FILESTORE TABLE", options: { bullet: true, breakLine: true } },
  { text: "One statement joins processor, webhook log, tickets and bank files", options: { bullet: true, breakLine: true } },
  { text: "3 to 9 queries per investigation, no ETL, no copies", options: { bullet: true } },
], { x: 0.5, y: 1.4, w: 5.0, h: 3.0, fontFace: BODY, fontSize: 16, color: WHITE, paraSpaceAfter: 10, valign: "top", margin: 0, isTextBox: true });
card(s, 5.8, 1.4, 3.7, 3.4, "Found by running it", "No DuckDB connector, so sources moved to Postgres.\n\nSpark SQL only: a Postgres-style query silently returned NULLs.\n\nLocal files must sit under the driver's shared root.", { fill: PANEL, headColor: MINT, color: "E8ECF1" });
footer(s, 7, true);

// 8 Nemotron and Meterless
s = pres.addSlide(); s.background = { color: PAPER };
title(s, "Nemotron writes it. Meterless checks it");
card(s, 0.5, 1.4, 4.3, 3.4, "NVIDIA Nemotron Ultra", "Writes the plain-language summary from the structured report.\n\nA validator rejects output that cites an unknown evidence id or contains a number not in the facts.\n\nIt never chooses queries or computes amounts.");
card(s, 5.2, 1.4, 4.3, 3.4, "Meterless Nightshift", "A second, independent model checks every sentence against the facts: PASS or FAIL.\n\nFAIL falls back to a template. The report shows the routed model and the compute receipt.\n\nTested on correct and deliberately wrong summaries.");
footer(s, 8);

// 9 Distinctive
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "What is distinctive");
card(s, 0.5, 1.4, 4.3, 1.6, "It tries to prove itself wrong", "Each cause gets a second query built to disprove it. Failed causes are dropped and listed.");
card(s, 5.2, 1.4, 4.3, 1.6, "Math in code", "Amounts, remainder and confidence are computed in Python from query results.");
card(s, 0.5, 3.2, 4.3, 1.6, "Honest uncertainty", "Unexplained money is reported as unexplained, not given an invented cause.");
card(s, 5.2, 3.2, 4.3, 1.6, "Read-only by design", "SQL guard, ticket text never reaches a query, humans approve every action.");
footer(s, 9);

// 10 Eval
s = pres.addSlide(); s.background = { color: PAPER };
title(s, "Measured, including the failure");
s.addText("2100 / 2100", { x: 0.5, y: 1.35, w: 4.4, h: 0.9, fontFace: HEAD, fontSize: 48, bold: true, color: EMERALD, margin: 0, isTextBox: true });
s.addText("21 scenarios on live Zetaris. 5 held out and never tuned against. Includes red herrings and two cases that must stay unexplained.", { x: 0.5, y: 2.3, w: 4.4, h: 1.2, fontFace: BODY, fontSize: 15, color: INK, valign: "top", margin: 0, isTextBox: true });
s.addText("First run on the 13 new scenarios: 1995 / 2100. A falsifier matched unrelated bank lines with round amounts. We fixed the logic and logged it in docs/EVAL_LOG.md.", { x: 0.5, y: 3.6, w: 4.4, h: 1.2, fontFace: BODY, fontSize: 14, italic: true, color: MUTED, valign: "top", margin: 0, isTextBox: true });
if (shot("eval.png")) s.addImage({ path: shot("eval.png"), x: 5.1, y: 1.35, w: 4.4, h: 3.5, sizing: { type: "contain", w: 4.4, h: 3.5 } });
footer(s, 10);

// 11 Screens
s = pres.addSlide(); s.background = { color: INK };
title(s, "The product", true);
if (shot("investigation.png")) s.addImage({ path: shot("investigation.png"), x: 0.5, y: 1.3, w: 4.4, h: 3.2, sizing: { type: "contain", w: 4.4, h: 3.2 } });
if (shot("report.png")) s.addImage({ path: shot("report.png"), x: 5.1, y: 1.3, w: 4.4, h: 3.2, sizing: { type: "contain", w: 4.4, h: 3.2 } });
s.addText("Live timeline with an evidence panel (left). Report with causes, confidence and approvals (right).", { x: 0.5, y: 4.65, w: 9, h: 0.4, fontFace: BODY, fontSize: 13, color: "C9D3E0", margin: 0, isTextBox: true });
footer(s, 11, true);

// 12 Limits and next
s = pres.addSlide(); s.background = { color: WHITE };
title(s, "Limits and what comes next");
card(s, 0.5, 1.4, 4.3, 3.4, "Limits, stated plainly", "Rules plus falsification, not an LLM planner.\n\nSix cause types covered; reversals, rounding, duplicate bank lines and chargebacks are not.\n\nSynthetic data. No public deployment: Zetaris runs locally.");
card(s, 5.2, 1.4, 4.3, 3.4, "Next", "More fault types and an independent held-out set.\n\nZetaris masking policies.\n\nAn LLM planner that proposes new checks inside the same SQL guard.\n\nA pilot with an African payments operator.");
footer(s, 12);

// 13 Close
s = pres.addSlide(); s.background = { color: INK };
s.addText("Ledgerwise", { x: 0.7, y: 1.5, w: 8.6, h: 0.9, fontFace: HEAD, fontSize: 48, bold: true, color: WHITE, margin: 0, isTextBox: true });
s.addText("Read-only. Evidence for every claim. Humans approve.", { x: 0.7, y: 2.5, w: 8.6, h: 0.6, fontFace: BODY, fontSize: 22, color: MINT, margin: 0, isTextBox: true });
s.addText("github.com/dev-ayomide/ledgerwise", { x: 0.7, y: 3.5, w: 8.6, h: 0.5, fontFace: BODY, fontSize: 18, color: "C9D3E0", margin: 0, isTextBox: true });

pres.writeFile({ fileName: path.join(__dirname, "Ledgerwise.pptx") }).then(() => console.log("wrote deck"));
