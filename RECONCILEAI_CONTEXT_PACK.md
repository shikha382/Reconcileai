# ReconcileAI — Complete Context Pack

Status: RESEARCH + PRODUCT DEFINITION ONLY. No code written. No application scaffold created. No milestone started.
Purpose: a single source-of-truth document another LLM/Codex session (or a human) can read and immediately understand the project, its evidence base, and its plan.
Research date: 2026-08-25. All web-sourced claims below were verified on this date; product pages change over time — re-verify before relying on this for a live submission close to a deadline.

Epistemic labeling used throughout: **FACT** (directly sourced, URL given), **INFERENCE** (a reasonable conclusion drawn from facts, explicitly mine), **HYPOTHESIS** (an unverified guess), **SECONDARY SOURCE** (from a non-official source — review site, blog, aggregator — treated with reduced confidence).

---

## 1. Buildathon Context

**FACT** — Official program: Razorpay AI Buildathon 2026, at https://razorpay.com/buildathon/ (verified live 2026-08-25). Framing: "Build. Show. Get hired." — "A student-only program to discover and hire our next generation of AI Builder Interns."

**FACT** — Format: pick a track → build something real → submit a public repo + a 5-minute pitch video + the architecture → shortlisted builders get a panel review ("No aptitude test. No group discussion.").

**FACT** — Compensation/logistics for selected builders: ₹75,000/month stipend, 6 or 12 months (builder's choice), in-person in Bangalore from September.

**FACT** — Rules: students only (program-wide). Track 02 is explicitly defense-only ("anything offense-capable is disqualified"). Track 01 requires Razorpay test-mode APIs. No blanket "no real financial data" rule was found for all tracks, but Track 04 specifically calls for synthetic data (see below).

**Application deadline — FACT via corroborated secondary sources**: Two independent secondary sources (an X/Twitter post and an independent blog, velonx.in) both state **September 5, 2026**. Not found verbatim on the official page itself in the content retrieved, so treat the exact date as corroborated-but-secondary, and confirm on the live registration page before treating it as locked.

**Team size** — **Not publicly documented / could not verify.** A secondary source explicitly flags this as unspecified. Confirm directly with organizers if it matters for planning.

**No numeric judging rubric is published.** Each track instead has an embedded "the bar" statement functioning as the judging criterion (quoted per-track below).

---

## 2. Problem Statement (exact, from the official track)

**FACT — verbatim from razorpay.com/buildathon/, Track 04:**

> **04 — AI Finance Controller**
> "Run the books and the cash position."
> Task: **"Build an agent that closes one finance-ops loop across a 50+ record batch of synthetic data, reporting its match rate and the exceptions it could not resolve."**
> Why now: "Reconciliation, settlement and forecasting are still done by hand."
> Example directions: **"Multi-source reconciliation, Settlement Q&A agent, Forward cash forecaster, Tax-line matcher."**
> The bar: **"Throughput plus measured accuracy plus an honest exception list. One cherry-picked match proves nothing."**

This is used verbatim and is not paraphrased or reinterpreted. ReconcileAI targets the **"Multi-source reconciliation"** example direction specifically, and commits to closing exactly **one** finance-ops loop, per the task's own wording ("one finance-ops loop").

For completeness, the other four tracks (not pursued, listed only so the choice is traceable): 01 AI Growth & Agentic Commerce, 02 AI Risk Manager, 03 AI Revenue Recovery, 05 Open Track. Full quotes available in the raw research transcript if needed later; omitted here to keep this document focused.

---

## 3. Track

**Razorpay AI Buildathon 2026 — Track 04: AI Finance Controller.** Confirmed exact match (Section 2). Not inferred, not substituted from a different year's program — no 2024/2025 edition of this specific "AI Buildathon" branding was found, so this is treated as a new/current program with no prior-year rubric to cross-check against.

---

## 4. User Problem

Grounded in the research (competitor docs, review-site complaints, Track 04's own "why now" line), the real pain points in reconciliation work are:

- **Manual, spreadsheet-driven matching** — explicitly named as the status quo Recko was built to replace (FACT, recko.io), and the exact "why now" Track 04 cites.
- **Multi-source fragmentation** — reconciling payment gateway data against internal ledgers, bank statements, and (for multi-PG merchants) multiple gateways at once (FACT, Razorpay Optimizer's whole premise; Osfin's "multiple data sources, payment rails, and lending systems" framing).
- **The hard residue after easy matches are done**: timing differences (settlement lag), fee/tax deductions, refunds, duplicates, partial/split settlements, many-to-one and one-to-many matches, ambiguous cases — this is the exact category every competitor researched (Stripe's own docs, Modern Treasury's G2 reviews) admits is where friction concentrates, not the easy 1:1 exact matches.
- **Opaque "AI-powered" black boxes** — Razorpay's own Recon product and Recko are marketed as AI-powered with zero disclosed methodology (no matching algorithm, no exception-workflow mechanics published). Finance teams are asked to trust a result they can't inspect.
- **No investigation, only detection** — every product surveyed either matches or flags a mismatch; none publicly document an agent that investigates *why* a mismatch happened using evidence from related records and explains the likely root cause before recommending a resolution.
- **Auditability** — reconciliation decisions affecting money need a trail (who/what/why), which is inconsistently disclosed across incumbents (Modern Treasury is the one exception with explicit human-in-the-loop AI-suggestion disclosure).

---

## 5. Research Findings — Summary

(Full detail in Sections 6–7 and the raw agent transcripts. Key cross-cutting findings:)

- A track literally named "AI Finance Controller" exists in the 2026 Buildathon and names multi-source reconciliation as an example direction — strong problem-statement fit, not an invented one.
- Razorpay already ships **three separate reconciliation-adjacent products** (POS "Razorpay Recon", Optimizer Single View Recon, plain Settlement Recon API) plus Smart Collect for bank-transfer collection reconciliation — none of which publicly disclose a matching methodology, and none of which (except the plain Settlement Recon API and Smart Collect) expose a public API.
- Across all competitors researched (Recko, Osfin, Modern Treasury, Stripe, BlackLine, Trintech), only **Modern Treasury** explicitly and credibly discloses an AI/deterministic boundary ("entirely deterministic" core matching, AI only for ambiguous-case suggestions, human-in-the-loop). This is the credibility benchmark to emulate, not the feature set to copy (Modern Treasury is US bank-rail-centric, not Razorpay/India-relevant).
- Open-source review shows two disconnected "species" of prior art: finance-domain reconciliation tools with simple rule-based matching (Blnk, Mint/ERPNext, bank-reconcile, the Shopify↔Razorpay toy project), and general-purpose probabilistic/ML matching libraries with zero finance semantics (Splink, dedupe, recordlinkage). **Nobody combines them.** That gap — rules for the easy majority, probabilistic/ML-assisted matching plus LLM-based investigation for the hard residual exceptions, with an audit trail — is the most evidenced whitespace found in this research (this conclusion is INFERENCE, clearly synthesized from the above facts, not itself sourced).
- One early multi-agent invoice-reconciliation demo (docsamajh-ai, 0 stars, unverified maturity) shows the "specialized agent per pipeline stage" pattern is already being explored elsewhere — useful as an architecture precedent, not as a technical reference to copy directly.

---

## 6. Competitor Analysis

| Product | Matching approach (as documented) | AI claim honesty | Exception handling | Razorpay/India relevance | Notable documented gap |
|---|---|---|---|---|---|
| **Recko** (recko.io, acquired by Stripe 2021, still live) | Not disclosed technically; INFERENCE (from Stripe's acquisition description) leans rule-based | Not claimed as AI/ML on Recko's own site; one secondary aggregator called it "AI-based" — unverified, likely marketing paraphrase | "Real-time analytics for discrepancies," no disclosed workflow detail | **High** — has a dedicated "Recko for Razorpay" connector (FACT) | No independent reviews found at all (G2/Capterra/HN) — a real research gap, not a confirmed weakness |
| **Osfin** (osfin.ai) | Hybrid, genuinely disclosed: AI for data extraction/normalization from PDFs/XML, **rule-based "validation rules" for the actual matching**, AI-flavored exception triage "based on historical trends and policies" (undisclosed methodology) | Partially substantiated — most honest of the India-centric players about where AI sits | Dedicated exception-management module with escalation/assignment | Medium — no confirmed Razorpay integration found; case study describes "a major Indian fintech" without naming Razorpay | No public review-site footprint (G2/Capterra/Gartner) found — limits independent verification |
| **Modern Treasury** | **Explicitly disclosed: "entirely deterministic" core engine; AI only makes suggestions in ambiguous cases the deterministic engine can't resolve with 100% certainty**, human-reviewed | **Most credible AI claim of all competitors researched** — scoped, honest, quoted directly from their own newsroom | Dedicated "Exception Management" capability | Low — US/ACH/wire-centric, not India/UPI-centric | G2 reviews (secondary): friction reconciling check deposits, no "un-reconcile," gaps in many-to-many check/EP matching |
| **Stripe** (Sigma + Payout Reconciliation report; invoicing auto-recon is **deprecated**) | Sigma = manual SQL querying, not automated matching. Payout Reconciliation = deterministic matching of payouts to transactions. Deprecated invoicing flow = memo-string + amount-fallback matching | No credible "AI reconciliation" claim found for Stripe specifically | Payout report explicitly does **not** cover instant payouts ("you're responsible for reconciling instant payouts") — a citable, self-disclosed gap | Low — not India/Razorpay-relevant | Its one "automatic reconciliation" feature is officially deprecated |
| **BlackLine / Trintech** | Rules-driven "Transaction Matching" core; AI ("Verity AI") added as a more recent overlay (secondary-sourced, one source with a conflict of interest) | Marketing-forward, weakly substantiated for the AI-specific claims | Workflow-heavy, enterprise-grade | Low — enterprise-only, reportedly $77K–$340K/yr (unverified secondary figure) | Not relevant to a hackathon-scale build; useful only as "how enterprise incumbents are structured" context |
| **Razorpay Recon (POS)** — the actual in-ecosystem incumbent | Undisclosed methodology; branded "AI-powered," "predictive analytics," "adaptive learning" with zero technical substantiation | **Least substantiated "AI" claim of any product researched** — no architecture, no algorithm class disclosed anywhere found | "Self-serve dashboard for identifying mismatches" — no disclosed exception workflow | Direct incumbent, not a competitor to differentiate against in the abstract — this is what a judge will compare ReconcileAI to | Dashboard-only, no public API found for the AI-Recon product itself |

Trovata and Tesorio were also researched but are cash/treasury-forecasting tools with reconciliation bolted on, not reconciliation-first products — included for completeness, not treated as close competitors.

---

## 7. Razorpay Recon Analysis (Razorpay's own reconciliation surfaces)

Four distinct, separately-branded surfaces exist inside Razorpay's own product line — conflating them would misrepresent the landscape:

1. **"Razorpay Recon"** (Razorpay POS, launched Dec 2024, FACT via https://razorpay.com/newsroom/...) — AI-branded, claims 200M transactions/month and "80% improvement in financial operations efficiency" (Razorpay's own unaudited figure). Covers online, offline, and custom reconciliation types. **No disclosed matching algorithm. No public API found.**
2. **Razorpay Optimizer — Single Reconciliation View** (https://razorpay.com/docs/payments/optimizer/reconciliation/) — consolidates transactions/refunds/settlements across *external* (non-Razorpay) gateways. Dashboard/report-only; **no disclosed exception mechanics, no API found.**
3. **Settlement Recon API** (https://razorpay.com/docs/api/settlements/fetch-recon/) — `GET /v1/settlements/recon/combined?year=&month=[&day=]` — the **one genuinely public, well-documented, developer-facing API** in this space. It is a plain data-fetch endpoint (payments/refunds/transfers/adjustments settled on a date) with **zero AI/matching logic of its own** — any intelligence has to be built on top of it by the caller. This is a strong candidate as ReconcileAI's real (or mock-mirrored) data source.
4. **Smart Collect 2.0** (https://razorpay.com/smart-collect/) — matches incoming UPI/IMPS/NEFT/RTGS transfers to virtual account IDs in real time, with automated refund-to-source as its exception path. Has APIs/webhooks (unlike #1 and #2).

**Conclusion (INFERENCE, not sourced):** Razorpay's own ecosystem has a real, public, structurally simple data source (#3) with no intelligence layer on top of it, and two AI-branded products (#1, #2) that are black boxes with no public API. ReconcileAI's most credible technical positioning is: **build the transparent, explainable intelligence layer that could sit on top of data shaped like Razorpay's own Settlement Recon API** — not compete head-on with the AI-Recon product's dashboard, but demonstrate the auditable reasoning that product doesn't disclose.

---

## 8. Differentiation

**The question the pack must answer: why would a judge care about ReconcileAI given Razorpay Recon already exists?**

Five defensible opportunities identified, none inventing a capability Razorpay Recon is confirmed to have:

1. **Disclosed methodology vs. black box.** Every Razorpay-ecosystem product (Recon, Optimizer, Recko) markets "AI" with zero disclosed matching logic. ReconcileAI can publish exactly what's deterministic vs. AI-assisted vs. agent-orchestrated — mirroring Modern Treasury's credible disclosure pattern, which no India/Razorpay-ecosystem player currently does.
2. **Investigate → Explain, not just Detect.** No product researched — Razorpay's own or any competitor — publicly documents an agent that gathers evidence from related records and explains the likely root cause of an exception before recommending a resolution. Every incumbent stops at "flagged as a discrepancy." This is the clearest, most evidenced whitespace in the entire research pass.
3. **Honest, measured exception reporting as the product's own success metric** — directly demanded by Track 04's bar itself ("measured accuracy plus an honest exception list... one cherry-picked match proves nothing"). This is a judging-criteria-aligned differentiator regardless of what any competitor does.
4. **API-first / developer-transparent** vs. dashboard-only. Razorpay's two AI-branded recon products are Dashboard-only with no public API; only the non-intelligent plain data API is public. An agent layer with a structured, inspectable output (JSON recommendation + confidence + evidence + audit entry) fills a gap none of the black-box dashboards address.
5. **Deterministic/AI safety boundary as a first-class, demoed feature** — aligns directly with the Buildathon's own cross-track safety framing ("every money action explainable, bounded and gated," seen in Track 01's bar) even though ReconcileAI targets Track 04. Demonstrating this boundary live is a credibility signal few (if any) competitor discloses convincingly.

**Recommended single positioning:** Lead with **#2 combined with #3** — *"ReconcileAI doesn't just flag mismatches, it investigates them: it gathers evidence from related records, explains the likely root cause, proposes a resolution with a confidence score, and reports an honest match rate and exception list — the exact bar Track 04 sets, and the one thing no reconciliation product researched (including Razorpay's own) currently discloses doing."* Use #1, #4, #5 as supporting proof points in the demo, not as the headline.

---

## 9. Product Definition

- **WHO uses it:** A finance-ops/reconciliation analyst at a merchant or payment-ops team (the persona Track 04 targets — someone currently reconciling "by hand").
- **WHAT problem do they have:** They have two or more record sets (e.g., internal ledger vs. Razorpay settlement export) that mostly match automatically, but a residual set of exceptions (timing, fees, refunds, duplicates, partial settlements, ambiguous cases) requires manual, undocumented investigation.
- **WHAT ReconcileAI does:** Ingests 50+ synthetic records across at least two sources, deterministically matches the easy majority, and for the unresolved residue runs an agent that investigates using evidence from related records, classifies the likely root cause, proposes a resolution with a confidence score, and either auto-resolves (if verification passes) or reports it as an honest unresolved exception.
- **WHY AI is actually needed:** The easy matches (exact ID + amount + date) need no AI — this is exactly the deterministic-first design every credible competitor (Modern Treasury) uses. AI/LLM reasoning is needed specifically for the residual, ambiguous cases where root cause isn't a simple rule (e.g., "is this a duplicate or a legitimate second charge?", "is this fee deduction expected or an error?") — cases that genuinely require synthesizing evidence across multiple related records and producing a natural-language rationale, which is what none of the researched competitors publicly disclose doing.
- **WHAT deterministic code handles:** normalization, exact/tolerance-window matching, arithmetic (fee/tax/balance checks), policy/threshold checks, final verification gating.
- **WHAT AI handles:** exception root-cause classification, evidence synthesis into an explanation, resolution recommendation with confidence — never the final financial decision.
- **WHAT the agent does:** orchestrates which evidence to gather (related refund records, fee schedules, duplicate candidates, prior settlement history) before invoking the reasoning step, and packages the result as a structured, machine-checkable recommendation (not free text) for the verification layer to gate.
- **WHAT the user sees:** an ingestion screen for the two-plus data sources; a results dashboard showing match rate and a categorized exception list; a drill-in view per exception showing the agent's gathered evidence, explanation, confidence score, and recommended resolution; an audit trail per decision; a final honest summary screen (match rate %, resolved count, unresolved count) — deliberately including at least one genuinely unresolved case, per the Track 04 bar's explicit warning against "one cherry-picked match."
- **End-to-end workflow:** Ingest → Normalize → Deterministic match pass → For unmatched: Agent investigates (gather evidence → classify → explain → recommend) → Verification layer (policy + confidence gate) → Auto-resolve or flag for human review → Audit log entry → Report match rate + exception list.

---

## 10. MVP

**CORE MVP** (the one finance-ops loop must work end-to-end on this alone):
- Ingest exactly two synthetic data sources (e.g., internal ledger + Razorpay-shaped settlement export) as CSV/JSON.
- Deterministic normalization + exact/tolerance matching pass, producing a match rate.
- A fixed taxonomy of exception types (timing difference, fee deduction, refund, duplicate, amount mismatch, missing record, partial settlement, ambiguous) applied to the unmatched residue.
- An agent/LLM investigation step for unmatched records: gather evidence from related records, classify root cause, explain, recommend a resolution, attach a confidence score.
- A verification/policy layer that gates any auto-resolution (confidence threshold + deterministic sanity checks) and marks anything below threshold as an honest "unresolved exception."
- An audit trail: every resolved-or-unresolved exception has a logged rationale.
- A results report: match rate %, resolved count, unresolved count, per-category breakdown — matching Track 04's bar directly.
- A minimal UI (even a simple dashboard) to show ingestion → results → drill-in on at least one exception live.

**IMPORTANT** (strengthens the core loop, build only after CORE MVP works end-to-end):
- Mock Razorpay Settlement Recon API layer, shaped to match the real `/v1/settlements/recon/combined` schema so it can later be pointed at live data without a rewrite.
- A slightly richer dashboard (filtering by exception category, sortable list).
- Explicit "what's deterministic vs. AI vs. agent vs. verification" boundary shown somewhere in the UI/demo (differentiation opportunity #5).

**OPTIONAL** (do not build unless CORE MVP + IMPORTANT are done and there's spare time):
- Settlement Q&A agent (a separate Track 04 example direction — out of scope for "one finance-ops loop," would dilute focus).
- Forward cash forecaster (also a separate Track 04 example direction — explicitly excluded, see Section 15).
- Tax-line matcher (same reasoning).
- A third data source beyond the two required for the core loop.
- Multi-way (3+ source) reconciliation.

**DEMO POLISH** (cosmetic only, last):
- Visual styling of the dashboard.
- A scripted/recorded walkthrough matching the 5-minute pitch video requirement.
- Sample data curated for a compelling but honest demo narrative (must still include at least one real unresolved exception, per the bar).

---

## 11. Dataset Design

**Scale:** ≥50 records minimum per Track 04's explicit requirement; recommend 60–80 to comfortably cover every exception category with more than one example each while staying within a demoable size.

**Sources (two, for the core loop):**
- **Source A — "Internal Ledger"**: `record_id, order_id, amount, currency, timestamp, status, customer_ref`
- **Source B — "Settlement Export"** (shaped after Razorpay's real Settlement Recon API fields, per Section 7 #3): `entity_id, type (payment/refund/transfer/adjustment), debit, credit, amount, currency, fee, tax, settled, settlement_id, payment_id, method, order_id`

**Ground truth:** a hidden third file (`ground_truth.json`) mapping each Source A record to its correct Source B match (or explicitly `null`/"no match exists") and its true exception category — used only for evaluation, never given to the matching/agent logic.

**Injected anomaly categories (each should appear multiple times, not once, to avoid a "cherry-picked" demo):**
- Exact matches (the majority — establishes the baseline match rate)
- Timing differences (settlement lag — same transaction, dates differ by 1–3 days)
- Fee deductions (settlement amount = ledger amount − fee, requiring arithmetic-aware matching)
- Refunds (a debit record with no corresponding original in the naive pass unless refund logic is applied)
- Duplicates (two settlement records for what should be one ledger record — tests whether the agent correctly identifies duplication vs. two legitimate charges)
- Missing records (a ledger entry with genuinely no settlement counterpart yet — should be correctly reported unresolved, not force-matched)
- Amount mismatches (a genuine data error — small currency/amount discrepancy with no clean explanation)
- Partial settlements (one ledger order split across two settlement records)
- Ambiguous cases (deliberately underdetermined — e.g., two candidate matches with identical amount and close timestamps) — these are the ones that should legitimately end up in the "unresolved" bucket, proving the system doesn't fake certainty.

**Expected results / evaluation metrics:**
- **Match rate** = exact + tolerance-matched records / total records (Track 04's own named metric).
- **Exception classification accuracy** = agent's assigned root-cause category vs. ground-truth category, for the unmatched residue.
- **False-resolution rate** = count of auto-resolved exceptions that were actually wrong per ground truth (target: 0, since the verification layer should have caught these — this is the single most important safety metric).
- **Honest-unresolved rate** = ambiguous ground-truth cases correctly left unresolved rather than force-matched (directly rewards NOT overclaiming certainty, per the bar's "one cherry-picked match proves nothing").
- **Audit completeness** = % of exceptions with a logged rationale (target: 100%).

---

## 12. AI / Agent Architecture

**Deterministic (no LLM involved):**
- Field normalization (currency formatting, date/timezone alignment, ID format alignment).
- Exact-match pass (reference/order ID + amount + date).
- Tolerance-window matching (amount within fee-adjusted range, date within a settlement-lag window).
- Arithmetic checks (fee/tax reconciliation, balance/sum checks for partial settlements).
- Final policy/threshold validation of any proposed resolution (currency match, amount sanity, non-negative checks, duplicate-resolution safety).

**AI (LLM, recommendation-only, never final authority):**
- Root-cause classification of an unmatched record against the fixed exception taxonomy.
- Explanation generation — a human-readable rationale citing the specific evidence used.
- Evidence synthesis across multiple related records (e.g., "this refund record plus this original payment plus the fee schedule together explain the mismatch").
- Resolution recommendation with an attached confidence score.

**Agent (orchestration layer):**
- Given an unmatched record, selects which evidence-gathering tools to call (e.g., "find candidate matches within tolerance," "look up related refund/duplicate records," "fetch fee schedule for this method/date") before invoking the LLM reasoning step.
- Packages the LLM's output as **structured JSON** (category, confidence, cited evidence, recommended action) — never free text — so the verification layer can programmatically check it.

**Verification (deterministic, gates every AI output before it becomes authoritative):**
- Confidence threshold: below threshold → forced into "unresolved exception," never auto-resolved.
- Policy checks: the recommended resolution must pass the same deterministic sanity checks as any other write (currency, amount, non-negative, no double-resolution of the same record).
- Human-approval flag: any resolution above a configurable dollar/complexity threshold requires explicit human sign-off before being marked "resolved" (mirrors Modern Treasury's disclosed human-in-the-loop pattern — Section 6).
- Audit trail: every record — resolved or unresolved — gets an immutable log entry: what evidence was gathered, what the AI concluded, what confidence it had, what the verification layer decided, and why.

This mirrors the Buildathon's own cross-track safety language ("every money action explainable, bounded and gated") even though that phrase is quoted from Track 01, not Track 04 — used here as a design principle, not a claimed requirement of Track 04 itself.

---

## 13. Technical Architecture

Kept deliberately simple and buildable by a student team in a Buildathon timeframe:

- **Frontend:** a lightweight React (or plain HTML/JS) dashboard — ingestion view, results/match-rate view, exception drill-in view, audit trail view. No need for a heavy framework or design system.
- **Backend:** a single Python (FastAPI) or Node (Express) service exposing ingestion, matching, and exception-resolution endpoints.
- **Database:** SQLite for the hackathon build (swappable to Postgres later without a rewrite) — stores raw records, match results, exceptions, audit log.
- **Reconciliation engine:** a plain deterministic module (no LLM dependency) implementing normalization, exact/tolerance matching, and arithmetic checks — independently testable against `ground_truth.json`.
- **AI/LLM layer:** a single LLM call per unresolved exception, given the record plus the evidence the agent gathered, returning structured JSON (category, explanation, confidence, recommended action).
- **Agent/tool layer:** a small, explicit set of "tools" (functions) the orchestration step can call — find-candidate-matches, find-related-refund, find-duplicate-candidates, fetch-fee-schedule — no need for a heavyweight agent framework; a simple function-calling loop is sufficient at this scale.
- **Razorpay integration/mock layer:** a mock data source shaped exactly like the real Settlement Recon API response (Section 7 #3), so the mock can later be replaced by a live API call without touching the reconciliation/agent logic — this satisfies the "mock-first, swappable" requirement directly.
- **Synthetic data generator:** a script producing the ≥50-record dataset plus `ground_truth.json` per Section 11's design (not yet built — design only, per current scope).
- **Evaluation layer:** a script comparing system output against `ground_truth.json` to compute match rate, classification accuracy, false-resolution rate, honest-unresolved rate.
- **Logging/audit layer:** an append-only log (a dedicated table, not just application logs) capturing every decision with its rationale, satisfying the audit-trail requirement.

---

## 14. Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| LLM hallucinates a plausible-sounding but wrong root cause / recommendation | High | Medium | Verification layer never treats LLM output as final; confidence threshold + deterministic policy checks gate every auto-resolution; structured JSON output (not free text) makes checking tractable |
| Demo looks like "just another matcher," fails to land the differentiation | High | Medium | Explicitly show the investigate→explain step live, with evidence and confidence visible on screen; state the deterministic/AI boundary out loud in the pitch |
| Financial arithmetic errors (float rounding, currency handling) | High | Low–Medium | Use integer minor-unit arithmetic (paise/cents), never floats, for all amount comparisons |
| No public Razorpay exception-resolution API to integrate against | Medium | High (confirmed by research — none of the AI-branded Recon products expose one) | Mock-first design against the one API that *is* public and documented (Settlement Recon API), explicitly designed to be swap-ready |
| Demo shows a suspiciously perfect 100% match rate | High (directly penalized by the bar: "one cherry-picked match proves nothing") | Medium if not deliberately guarded against | Dataset design (Section 11) intentionally includes ambiguous cases that *should* end up genuinely unresolved; report them honestly on stage |
| Scope creep into the other Track 04 example directions (Settlement Q&A, cash forecasting, tax matching) | Medium | Medium | Explicit exclusion list (Section 15); "one finance-ops loop" is in the task text itself |
| Competitor-positioning risk — a judge asks "doesn't Razorpay already have this?" | Medium | High (should be expected) | Section 8's positioning statement rehearsed and ready; cite the specific disclosed gap (no methodology, dashboard-only, detect-but-don't-investigate) |
| Team-size / eligibility rule unclear (unconfirmed team-size policy) | Low | Low | Confirm directly via the official registration form before finalizing team composition |

---

## 15. What NOT to Build (strict exclusion list)

- A generic chatbot / open-ended Q&A interface (the "Settlement Q&A agent" direction is a *separate* Track 04 example — building it would dilute the "one finance-ops loop" focus, not strengthen it).
- Forward cash forecasting (also a separate named example direction — explicitly out of scope for this MVP).
- A tax-line matcher (same reasoning — a distinct example direction, not part of this loop).
- Any fraud-detection engine (that is Track 02's territory, not Track 04's).
- A full ERP or ledger platform (Blnk-style full double-entry ledger is a reference pattern to learn from, not a component to build wholesale — Section 6/open-source findings explicitly warn against this).
- Enterprise features: multi-tenant auth/billing, role hierarchies, SSO, etc. — not needed for a single-team hackathon demo.
- Real production Razorpay API integration with live credentials (mock-first per the brief; a real integration is a stretch goal only after the mock-swap design is proven, and only with explicit test-mode credentials, never production financial data).
- Multi-way (3+ source) reconciliation, or a third data source beyond the two needed for the core loop.
- Any feature that doesn't directly strengthen Detect → Investigate → Explain → Resolve → Verify for the one chosen loop.

---

## 16. Demo Plan

1. Show ingestion of the two synthetic sources (≥50 records total).
2. Run the deterministic pass; show the resulting match rate live (not pre-computed).
3. Drill into the exception list, grouped by category.
4. Pick one ambiguous/hard exception live and walk through the agent's process: evidence gathered → root-cause classification → explanation → recommendation → confidence score.
5. Show the verification layer either auto-resolving it (if confidence is high and policy passes) or correctly flagging it for human review (if not) — deliberately choose one exception that ends up genuinely unresolved, to honor the bar's "no cherry-picking" requirement live.
6. Show the audit trail entry for that decision.
7. End on the honest summary screen: match rate %, resolved count, unresolved count, per-category breakdown.
8. Close with the one-sentence differentiation pitch (Section 8).

---

## 17. Success Metrics

- **Match rate** on the ≥50-record synthetic batch (Track 04's own named metric).
- **Exception classification accuracy** vs. ground truth.
- **False-resolution rate** — target 0 (no auto-resolved exception should ever be wrong per ground truth; this is the key safety metric a judge evaluating "bounded and gated" behavior would look for).
- **Honest-unresolved rate** — genuinely ambiguous cases correctly left unresolved rather than force-matched.
- **Audit completeness** — 100% of exceptions (resolved or not) carry a logged rationale.

---

## 18. Recommended Milestone Roadmap (for later approval — NOT started)

This is a recommendation to review and approve before any implementation begins, one milestone at a time, per the incremental-build process already agreed for this project.

- **Milestone 0 — Project memory setup**: `AGENTS.md`, `docs/RECONCILEAI_SPEC.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`, using this Context Pack as source of truth. Documentation only, no application code.
- **Milestone 1 — Deterministic reconciliation core** — CORE MVP. Ingest two sources, normalize, exact + tolerance matching, produce a match rate. Independently testable against a small hand-built fixture before the full synthetic dataset exists.
- **Milestone 2 — Synthetic dataset + ground truth** — CORE MVP. Build the ≥50-record dataset and `ground_truth.json` per Section 11.
- **Milestone 3 — Exception taxonomy + evaluation layer** — CORE MVP. Fixed categories, and a script scoring system output against ground truth (match rate, classification accuracy, false-resolution rate).
- **Milestone 4 — Agent evidence-gathering tools** — CORE MVP. The small tool set (find-candidate-matches, find-related-refund, find-duplicate-candidates, fetch-fee-schedule).
- **Milestone 5 — LLM investigation/explanation step** — CORE MVP. Structured-JSON root-cause classification, explanation, recommendation, confidence — wired to the tools from Milestone 4.
- **Milestone 6 — Verification/policy layer + audit trail** — CORE MVP. Confidence gating, policy checks, human-approval flag, immutable audit log. (High priority — this is the safety boundary the whole positioning depends on.)
- **Milestone 7 — Minimal dashboard UI** — IMPORTANT. Ingestion, results, drill-in, audit views.
- **Milestone 8 — Mock Razorpay Settlement Recon layer** — IMPORTANT. Schema-matched mock, swap-ready design.
- **Milestone 9 — Demo polish** — DEMO POLISH. Recorded walkthrough, narrative, visual polish.
- **Explicitly deferred / OPTIONAL, not on this roadmap unless later approved:** Settlement Q&A agent, forward cash forecaster, tax-line matcher, third data source, multi-way reconciliation.

---

## Source Index (primary sources cited above)

- https://razorpay.com/buildathon/ — official Buildathon page, all track/rule/deadline-adjacent quotes
- https://razorpay.com/newsroom/razorpay-pos-launches-industry-first-ai-powered-razorpay-recon-to-automate-reconciliation-for-businesses-boosting-financial-operations-efficiency-by-80/
- https://razorpay.com/blog/revolutionizing-financial-reconciliation-with-razorpay-recon/
- https://razorpay.com/docs/payments/optimizer/reconciliation/ , https://razorpay.com/docs/payments/optimizer/
- https://razorpay.com/blog/single-view-recon/
- https://razorpay.com/docs/api/settlements/fetch-recon/
- https://razorpay.com/smart-collect/
- https://www.recko.io/ , https://www.recko.io/blog/recko-razorpay-integration/ , https://stripe.com/newsroom/news/recko
- https://www.osfin.ai/ , https://www.osfin.ai/solutions/fintech
- https://www.moderntreasury.com/solutions/reconciliation , https://www.moderntreasury.com/newsroom/press-releases/modern-treasury-enhances-reconciliation-engine-with-ai
- https://docs.stripe.com/reports/payout-reconciliation , https://docs.stripe.com/invoicing/automatic-reconciliation (deprecated), https://docs.stripe.com/data/how-sigma-works
- https://github.com/blnkfinance/blnk , https://github.com/The-Commit-Company/mint , https://github.com/dedupeio/dedupe , https://github.com/moj-analytical-services/splink , https://github.com/J535D165/recordlinkage , https://github.com/imrexankit/shopify-razorpay , https://github.com/mrioan/transaction-reconciliation , https://github.com/oprekable/bank-reconcile , https://github.com/marjan-ahmed/docsamajh-ai

Secondary sources (G2, Capterra, Trustpilot, aggregator blogs) are cited inline in the fuller agent transcripts where used; all are flagged as reduced-confidence in the sections above and none were treated as fact without that flag.
