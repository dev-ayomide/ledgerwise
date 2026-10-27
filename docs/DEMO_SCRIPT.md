# Demo script (target 3:00, limit 4:00)

Before recording: do not rotate the Nightshift key; keep Nightshift running; Zetaris running, `LEDGERWISE_GATEWAY=zetaris` server up on :8765, dashboard opened once so it is cached, a successful run already saved (backup: replay from the dashboard).

1. **0:00 to 0:20, the problem.** "When the processor, the ledger, the bank file and support disagree, nobody can say why. Ops teams spend hours on it, and the money stays missing."
2. **0:20 to 0:40, dashboard.** Show 21 Oct flagged NGN 4,200,000. Point at the badge: data comes through Zetaris federated SQL. Click Investigate.
3. **0:40 to 2:00, investigation.** Narrate as it streams:
   - First query joins four logical sources in one statement. Point at "Sources touched".
   - Plan, then one query per check, each with sources and row counts.
   - A hypothesis appears: "could explain NGN 700,000". Then the falsification step: "now it tries to prove itself wrong." Show one that survives (retry sequence in the webhook log).
   - Click an evidence id: show the SQL and the rows.
   - Reconciliation line: computed in code, unexplained NGN 0.00.
4. **2:00 to 2:30, report.** Bar of gap by cause, confidence per cause, "Tried to disprove" text. Approve one action: draft appears, banner says nothing is sent. Export Markdown.
5. **2:30 to 2:50, honesty.** Show `eval/results/latest.md`: 21 scenarios, 2100/2100 on live Zetaris. Say the first run on the new scenarios scored 1995/2100 and a falsifier bug caused it (EVAL_LOG). Say the rules are deterministic and cover six cause types.
6. **2:50 to 3:00, close.** "Built on Zetaris federation. Read-only, evidence for every claim, humans approve." Say: Nemotron Ultra writes the summary from structured evidence, a second model through Meterless Nightshift checks it, and amounts always come from code. Show the report line with the Meterless receipt.

Backup: replay a saved investigation from the dashboard (Replay), fixed seed 20261022.
