# Eval log

How to run: `.venv/bin/python -m backend.eval --gateway zetaris` (live federated) or `--gateway local` (DuckDB test double). Results land in `eval/results/latest.json` and `latest.md`.

Scoring (backend/eval.py): start at 100. Minus 10 for a wrong gap, minus 10 for a wrong unexplained remainder, minus 25 per false-positive cause, minus 25 per missed cause, minus 25 for a wrong amount (tolerance 1 kobo).

## 2026-10-27 run 1: 21 scenarios, local gateway, before any fix

Result: 1995/2100. Saved as `eval/results/run1_21_scenarios_before_fix.md`.

Three scenarios failed, all for one reason: the `partial_settlement` falsifier asked "does any bank line carry this amount?" and round amounts (30,000,000 and 40,000,000 kobo) collided with unrelated lines from other days. It dropped true causes. The three failures were `single-partial-2026-10-19`, `combo-two-part-dupl-2026-10-23`, `combo-two-part-unat-2026-10-29`. None are held-out scenarios.

Fix: the falsifier now only counts orphan lines, meaning same amount and a reference that matches no processor transaction. This is a logic fix, not a scenario-specific rule.

Earlier, before this log existed: the 8-scenario eval was reported as 100/100 in the README but the test suite showed `single-duplicate-2026-10-14` at 75. The cause was exact-match joins failing on messy bank references (lower case, `REF/` prefix), which produced a false `partial_settlement`. Fixed by normalising references in every query, and by no longer clamping the unexplained remainder at zero.

## 2026-10-27 run 2: 21 scenarios, Zetaris, after the fix

Result: 2100/2100 on live Zetaris (processor and events/support in two Postgres databases, bank files as Parquet). Local gateway also 2100/2100.

Held-out set: 5 scenarios (`combo-two-cuto-dupl-2026-10-01`, `combo-two-part-cuto-2026-10-05`, `combo-three-cuto-dupl-fee_-2026-10-11`, `combo-two-dupl-unat-2026-10-28`, `red-herring-2026-10-27`) were written after the detectors and not tuned against. All five passed on the first run. The other 16 were used while developing.

What this does not show:

- The detectors are rule-based and the scenarios come from the same generator and the same author. A perfect score means the rules match the injected fault catalog. It says little about messier real data.
- Fault types not implemented: reversal without ledger entry, rounding differences, duplicate bank lines, missing-webhook tickets as a cause, chargebacks. Six causes are covered: duplicate webhook, cutoff, fee mismatch, partial settlement, stuck pending, header discrepancy.
- Two scenarios include an unattributable short payment (12% and 12.5% of net). The agent reports them as unexplained instead of inventing a cause. A short payment under 5% of net would be labelled a fee mismatch, because the fee query accepts any shortfall up to 5%. That is a known weakness, not tested.
- Cost and latency: about 3 to 9 queries per investigation. The demo day takes roughly 4 s on Zetaris. No LLM tokens are used in the scoring path.
