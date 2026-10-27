/* Ledgerwise UI. Plain JS, no build step. Event types mirror backend/agent/events.py. */
"use strict";

const SOURCE_COLORS = {
  "Processor DB (Postgres)": "var(--c1)",
  "Webhook log (Postgres)": "var(--c2)",
  "Support tickets (Postgres)": "var(--c3)",
  "Bank settlement files (Parquet)": "var(--c4)",
};
const CODE_LABEL = {
  partial_settlement: "Missing bank line",
  cutoff_timezone: "Cutoff / timezone shift",
  duplicate_webhook: "Duplicate webhook credit",
  fee_mismatch: "Fee rate mismatch",
  stuck_pending: "Stuck pending transaction",
  header_discrepancy: "Batch header mismatch",
};
const CODE_COLOR = {
  partial_settlement: "var(--c1)", cutoff_timezone: "var(--c2)", duplicate_webhook: "var(--c3)",
  fee_mismatch: "var(--c4)", stuck_pending: "var(--c5)", header_discrepancy: "var(--c6)",
};

const state = { config: null, evidence: {}, events: [], investigationId: null, report: null, actions: [], touched: new Set() };

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}

/* Display only. Amounts stay integers (kobo) everywhere else. */
function ngn(kobo) {
  const neg = kobo < 0; const a = Math.abs(kobo);
  const naira = Math.floor(a / 100), rem = String(a % 100).padStart(2, "0");
  return (neg ? "-" : "") + "NGN " + naira.toLocaleString("en-US") + "." + rem;
}

function show(view) {
  for (const v of ["dashboard", "investigation", "report"]) {
    document.getElementById("view-" + v).hidden = v !== view;
    document.getElementById("tab-" + v).setAttribute("aria-selected", String(v === view));
  }
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));

async function loadConfig() {
  state.config = await (await fetch("/api/config")).json();
  const b = document.getElementById("badges");
  b.replaceChildren(
    h("span", { class: "badge " + (state.config.gateway === "zetaris" ? "ok" : "warn") },
      state.config.gateway === "zetaris" ? "Data: Zetaris federated SQL" : "Data: local DuckDB (test only)"),
    h("span", { class: "badge " + (state.config.llm ? "ok" : "warn") },
      state.config.llm ? "Summary model: " + state.config.llm : "Summary: template (no LLM configured)"),
    h("span", { class: "badge ok" }, "Read-only · humans approve actions"),
  );
}

async function renderDashboard() {
  const root = document.getElementById("view-dashboard");
  root.replaceChildren(h("p", { class: "muted" }, h("span", { class: "spinner" }), " Loading settlement summary through the data layer…"));
  let rows;
  try {
    const r = await fetch("/api/dashboard");
    if (!r.ok) throw new Error((await r.text()).slice(0, 300));
    rows = await r.json();
  } catch (e) {
    root.replaceChildren(h("div", { class: "note" }, "Could not load the dashboard: " + e.message));
    return;
  }
  const demo = rows.find((r) => r.scenario_id.startsWith("demo-")) || rows[0];
  rows = [demo, ...rows.filter((r) => r !== demo)];
  const input = h("input", { id: "q", "aria-label": "Question", value: demo.question });
  let date = demo.business_date;
  const go = h("button", { class: "btn", onclick: () => startInvestigation(input.value, date) }, "Investigate");
  const table = h("table", {},
    h("thead", {}, h("tr", {}, ["Value date", "Processor expects", "Bank settled", "Gap", ""].map((t, i) => h("th", { class: i > 0 && i < 4 ? "num" : "" }, t)))),
    h("tbody", {}, rows.map((r) => h("tr", {},
      h("td", {}, r.business_date, r === demo ? h("span", { class: "badge ok", style: "margin-left:8px" }, "demo") : ""),
      h("td", { class: "num" }, r.expected),
      h("td", { class: "num" }, r.actual),
      h("td", { class: "num " + (r.gap_kobo !== 0 ? "gap-flag" : "") }, r.gap_kobo !== 0 ? "⚑ " + r.gap : r.gap),
      h("td", {}, h("button", { class: "btn secondary", onclick: () => { input.value = r.question; date = r.business_date; startInvestigation(r.question, r.business_date); } }, "Investigate"))))));
  const past = await (await fetch("/api/investigations")).json();
  root.replaceChildren(
    h("h1", {}, "Settlement summary"),
    h("p", { class: "muted" }, "Each row is one value date, queried live across the processor database, the webhook log and the bank settlement files."),
    h("div", { class: "ask" }, input, go),
    h("div", { class: "panel" }, table),
    past.length ? h("div", { class: "panel", style: "margin-top:16px" }, h("h2", {}, "Replay a past investigation"),
      past.slice(0, 5).map((p) => h("div", {}, h("button", { class: "chip", onclick: () => replay(p.id) }, "▶ " + p.business_date + " · " + p.id), " ", h("span", { class: "muted" }, p.question)))) : "",
  );
}

function resetRun() {
  state.evidence = {}; state.events = []; state.report = null; state.actions = []; state.touched = new Set(); state.investigationId = null;
  document.getElementById("timeline").replaceChildren();
  document.getElementById("evidence-body").replaceChildren();
  document.getElementById("evidence-empty").hidden = false;
  document.getElementById("tab-report").disabled = true;
  renderSources();
  show("investigation");
}

function renderSources() {
  document.getElementById("sources").replaceChildren(
    h("strong", {}, "Sources touched: "),
    ...Object.entries(SOURCE_COLORS).map(([name, color]) =>
      h("span", { class: "src" + (state.touched.has(name) ? " on" : ""), style: state.touched.has(name) ? "background:" + color : "" }, name)),
  );
}

async function startInvestigation(question, date) {
  resetRun();
  add(h("li", { class: "item" }, h("span", { class: "spinner" }), " Starting investigation for " + date + "…"));
  try {
    const r = await fetch("/api/investigate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, business_date: date }) });
    if (!r.ok) throw new Error((await r.text()).slice(0, 300));
    await readStream(r.body);
  } catch (e) {
    add(h("li", { class: "item error" }, h("div", { class: "kind" }, "Error"), e.message));
  }
}

async function replay(id) {
  resetRun();
  const r = await fetch("/api/investigations/" + id + "/replay?delay=0.35");
  state.investigationId = id;
  await readStream(r.body);
}

async function readStream(body) {
  const reader = body.getReader(); const dec = new TextDecoder(); let buf = "";
  document.getElementById("timeline").replaceChildren();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
      if (chunk.startsWith("data: ")) handle(JSON.parse(chunk.slice(6)));
    }
  }
}

function add(node) {
  const tl = document.getElementById("timeline");
  tl.append(node);
  node.scrollIntoView({ block: "nearest" });
}

function evChips(ids) {
  return h("div", { class: "chips" }, (ids || []).map((id) => h("button", { class: "chip", onclick: () => inspect(id), "aria-label": "Open evidence " + id }, id)));
}

function inspect(id) {
  const e = state.evidence[id]; if (!e) return;
  document.getElementById("evidence-empty").hidden = true;
  const body = document.getElementById("evidence-body");
  body.replaceChildren(
    h("h2", {}, id + " · " + e.purpose),
    h("p", { class: "muted" }, e.sources.join(" + ") + " · " + e.row_count + " row(s) · " + e.duration_ms + " ms · " + e.engine),
    h("strong", {}, "Query"), h("pre", {}, e.sql),
    h("strong", {}, "Rows" + (e.truncated ? " (first 50)" : "")),
    rowsTable(e.columns, e.rows),
  );
}

function rowsTable(cols, rows) {
  if (!rows.length) return h("p", { class: "muted" }, "No rows returned.");
  return h("div", { class: "rows" }, h("table", {}, h("thead", {}, h("tr", {}, cols.map((c) => h("th", {}, c)))),
    h("tbody", {}, rows.map((r) => h("tr", {}, cols.map((c) => h("td", {}, String(r[c] ?? ""))))))));
}

function handle(ev) {
  state.events.push(ev);
  const d = ev.data;
  switch (ev.type) {
    case "investigation_started":
      state.investigationId = d.investigation_id || state.investigationId;
      add(h("li", { class: "item" }, h("div", { class: "kind" }, "Question"), d.question));
      break;
    case "plan":
      add(h("li", { class: "item plan" }, h("div", { class: "kind" }, "Plan"), h("p", {}, d.direction),
        h("ol", {}, d.checks.map((c) => h("li", {}, h("strong", {}, c.label), " · ", c.why)))));
      break;
    case "query_started":
      add(h("li", { class: "item query", id: "q-" + d.evidence_id }, h("div", { class: "kind" }, "Query " + d.evidence_id), d.purpose, " ", h("span", { class: "spinner" })));
      break;
    case "query_result": {
      state.evidence[d.id] = d;
      d.sources.forEach((s) => state.touched.add(s)); renderSources();
      const li = document.getElementById("q-" + d.id);
      if (li) li.replaceChildren(h("div", { class: "kind" }, "Query " + d.id + " · " + d.sources.length + " source(s) · " + d.row_count + " rows · " + d.duration_ms + " ms"),
        d.purpose, evChips([d.id]));
      if (d.id === "E1") inspect("E1");
      break;
    }
    case "finding":
      add(h("li", { class: "item finding" }, h("div", { class: "kind" }, "Finding"), d.text, evChips(d.evidence_ids)));
      break;
    case "hypothesis":
      add(h("li", { class: "item hypothesis" }, h("div", { class: "kind" }, "Hypothesis"),
        h("strong", {}, d.label), " could explain ", h("strong", {}, ngn(d.amount_kobo)), evChips(d.evidence_ids)));
      break;
    case "falsification_attempt":
      add(h("li", { class: "item falsify" }, h("div", { class: "kind" }, "Trying to prove it wrong · " + (CODE_LABEL[d.code] || d.code)), d.approach));
      break;
    case "falsification_result":
      add(h("li", { class: "item " + (d.survived ? "survived" : "dropped") }, h("div", { class: "kind" }, d.survived ? "Survived" : (d.survived === false ? "Dropped" : "Inconclusive") + " · " + (CODE_LABEL[d.code] || d.code)), d.note, evChips(d.evidence_ids)));
      break;
    case "math_summary":
      add(h("li", { class: "item math" }, h("div", { class: "kind" }, "Reconciliation (computed in code)"),
        "Gap " + ngn(d.gap_kobo) + " · explained " + ngn(d.explained_kobo) + " · unexplained ", h("strong", {}, ngn(d.unexplained_kobo))));
      break;
    case "report":
      state.report = d;
      add(h("li", { class: "item finding" }, h("div", { class: "kind" }, "Report ready"), h("button", { class: "btn", onclick: () => { renderReport(); show("report"); } }, "Open report")));
      document.getElementById("tab-report").disabled = false;
      renderReport();
      break;
    case "actions_proposed":
      state.actions = d.actions; renderReport(); break;
    case "error":
      add(h("li", { class: "item error" }, h("div", { class: "kind" }, "Error"), d.message)); break;
    case "investigation_finished":
      state.finished = d; renderReport(); break;
  }
}

function renderReport() {
  const r = state.report; if (!r) return;
  const root = document.getElementById("view-report");
  const total = Math.abs(r.gap_kobo) || 1;
  const segs = r.causes.map((c) => ({ label: CODE_LABEL[c.code], v: c.amount_kobo, color: CODE_COLOR[c.code] }));
  if (r.unexplained_kobo > 0) segs.push({ label: "Unexplained", v: r.unexplained_kobo, color: "var(--bad)" });
  const bar = h("div", { class: "bar", role: "img", "aria-label": "Gap explained by cause" },
    segs.map((s) => h("div", { style: "width:" + Math.max(0.5, (s.v * 100) / total) + "%;background:" + s.color, title: s.label + " " + ngn(s.v) }, (s.v * 100) / total > 9 ? Math.round((s.v * 100) / total) + "%" : "")));
  const legend = h("div", { class: "legend" }, segs.map((s) => h("span", {}, h("i", { style: "background:" + s.color }), s.label + " " + ngn(s.v))));

  root.replaceChildren(
    h("h1", {}, "Report · " + r.business_date),
    h("div", { class: "grid2" },
      h("div", { class: "panel" }, h("div", { class: "muted" }, "Gap to explain"), h("div", { class: "big" }, ngn(r.gap_kobo))),
      h("div", { class: "panel" }, h("div", { class: "muted" }, "Explained by evidence"), h("div", { class: "big" }, ngn(r.gap_kobo === 0 ? 0 : Math.abs(r.gap_kobo) - r.unexplained_kobo))),
      h("div", { class: "panel" }, h("div", { class: "muted" }, "Unexplained remainder"), h("div", { class: "big", style: r.unexplained_kobo ? "color:var(--bad)" : "" }, ngn(r.unexplained_kobo)))),
    h("div", { class: "panel", style: "margin-top:14px" }, h("h2", {}, "Gap by cause"), bar, legend),
    h("div", { class: "panel", style: "margin-top:14px" }, h("h2", {}, "Summary"), h("p", {}, r.narrative.text),
      h("p", { class: "muted" }, "Written by: " + r.narrative.source + ". Amounts come from code, not from the model."),
      verificationLine(r.narrative.verification)),
    h("div", { class: "panel", style: "margin-top:14px" }, h("h2", {}, "Root causes, largest first"),
      r.causes.length ? h("table", {}, h("thead", {}, h("tr", {}, ["Cause", "Amount", "Confidence", "Why we believe it", "Evidence"].map((t) => h("th", {}, t)))),
        h("tbody", {}, r.causes.map((c) => h("tr", {},
          h("td", {}, h("strong", {}, CODE_LABEL[c.code])),
          h("td", { class: "num" }, ngn(c.amount_kobo)),
          h("td", {}, h("span", { class: "conf " + c.confidence }, c.confidence)),
          h("td", {}, c.summary, h("br"), h("em", {}, "Tried to disprove: "), c.falsification_note),
          h("td", {}, evChips(c.evidence_ids)))))) : h("p", {}, "No cause found. Nothing in the available data explains a gap for this date.")),
    r.dropped.length ? h("div", { class: "note", style: "margin-top:14px" }, "Dropped after falsification: " + r.dropped.map((d) => CODE_LABEL[d.code] + " (" + d.note + ")").join("; ")) : "",
    h("div", { class: "panel actions", style: "margin-top:14px" }, h("h2", {}, "Proposed actions"),
      h("p", { class: "note" }, "The agent only proposes. Approving creates a draft document. Nothing is sent, posted or changed in any system."),
      ...(state.actions || []).map(actionCard)),
    h("p", { style: "margin-top:14px" },
      state.investigationId ? h("a", { class: "btn secondary", href: "/api/investigations/" + state.investigationId + "/export", target: "_blank", rel: "noopener" }, "Export Markdown") : null,
      " ", h("button", { class: "btn secondary", onclick: () => state.investigationId && replay(state.investigationId) }, "Replay investigation")),
    h("p", { class: "muted" }, (state.finished ? state.finished.query_count + " queries · " + state.finished.duration_ms + " ms · engine " + state.finished.engine : "")),
  );
}

function verificationLine(v) {
  if (!v || v.status === "not_configured") return "";
  const label = { pass: "passed", fail: "failed, template used instead", unavailable: "unavailable (" + (v.detail || "no answer") + ")", unclear: "unclear" }[v.status] || v.status;
  return h("p", { class: "muted" }, "Independent check by Meterless (" + (v.model || "") + "): " + label + (v.trace && v.trace.latency_ms ? " · " + v.trace.latency_ms + " ms" : "") + (v.trace && v.trace.routed_to ? " · routed to " + v.trace.routed_to : "") + (v.trace && v.trace.receipt_id ? " · receipt " + v.trace.receipt_id : ""));
}

function actionCard(a) {
  const out = h("div", {});
  const mk = (decision) => async () => {
    if (!state.investigationId) return;
    const res = await fetch("/api/investigations/" + state.investigationId + "/actions/" + a.id, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }) });
    const j = await res.json();
    out.replaceChildren(decision === "approve"
      ? h("div", {}, h("strong", {}, "Approved. Draft created, not sent."), h("div", { class: "draft" }, j.draft))
      : h("strong", {}, "Rejected."));
  };
  return h("div", { style: "margin-top:12px;border-top:1px solid var(--line);padding-top:10px" },
    h("strong", {}, a.title), " · " + ngn(a.amount_kobo),
    h("div", { class: "row" }, h("button", { class: "btn", onclick: mk("approve") }, "Approve draft"), h("button", { class: "btn danger", onclick: mk("reject") }, "Reject")),
    out);
}

(async function init() {
  await loadConfig();
  await renderDashboard();
})();
