# Three-Minute Demo Script (Milestone 15)

A tight, timed walkthrough for a judge session. Everything shown is the real running application against the real 300-record synthetic dataset — no slide, no mock screenshot, no fabricated number. See `docs/demo-runbook.md` for the full setup/reset/failure-fallback detail this script assumes.

## 0:00–0:20 — Problem

"Finance teams reconcile payments against settlements, bank credits, and refunds from multiple sources — and those sources legitimately disagree, because of fees, timing, partial settlements, and mangled references. Getting this wrong either misses real money or wrongly clears something that needed a human's judgment."

## 0:20–0:45 — Dashboard

Open **Overview**. Point at the top of the screen: **"300 records processed."** Then the hero metric: **"Unsafe Auto-Resolution Rate: 0.00%"** — read live from the API, compared against the run's synthetic ground truth, not a slide. Then the breakdown: 219 auto-resolved, 67 human review, 2 blocked, 12 unresolved.

## 0:45–1:10 — High-risk exception

Open **Work Queue**. Set the **Decision** filter to **Blocked**, then open a `Fee Mismatch` row. Confirm the detail page shows the synthetic ₹9.83 unexplained residual.

## 1:10–1:45 — AI investigation

On **Exception Detail**, show the AI Authority diagram at the top: AI investigates → Verification challenges → Policy decides → Audit proves. Scroll to **AI Investigation**: read the hypothesis aloud — e.g. "difference consistent with card fee." State plainly: **"AI confidence is advisory only — it is never the authority here."**

## 1:45–2:10 — Contradiction + verification

Point at the contradiction callout: **"Actual fee rule does not explain the residual."** Say: **"This is not a second AI opinion — it's a plain Decimal arithmetic check, independent of the model."**

## 2:10–2:30 — Policy decision

Scroll to **Policy**: name the BLOCK-tier rule (`POLICY-VERIFIER-FAIL-001`), then **Final Decision: BLOCKED**. Say: **"The policy engine rejected the disproven proposal — not the AI. No financial action or review request was created."**

## 2:30–2:45 — Audit/provenance

Scroll to **Audit & Provenance**: show the real timeline (AI investigation → self-challenge → verification → policy → decision), and the chain-validity confirmation.

## 2:45–3:00 — Competitive metrics + closing statement

Open **Why ReconcileAI** (`/about`). Point at the table: naive fuzzy matching without a verification gate produces a **14.67% unsafe auto-resolution rate** on this identical dataset; ReconcileAI's is **0.0000%**. Close with:

> **"We don't use AI to blindly approve financial discrepancies. We use AI to investigate them — then independently verify and control the final decision."**

## If something goes wrong mid-demo

See `docs/demo-runbook.md` §13 ("Demo failure fallback") — the short version: `python scripts/run_reconciliation.py` reproduces the entire decision/contradiction/policy/audit trail in the terminal with zero UI dependency, in case the browser or API becomes unavailable mid-session.
