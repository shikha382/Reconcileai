# Presentation Blueprint (Milestone 17)

No PPT/deck file exists anywhere in this repository (checked: no `.ppt`/`.pptx`/`.key` files, no `deck*` files). This is the recommended slide-by-slide structure, built only from what this project can actually prove — every slide below cites the real doc/number it should pull from, never a number invented for the deck.

## Recommended structure (PROBLEM → WHY EXISTING APPROACH FAILS → RECONCILEAI → ARCHITECTURE → AI ROLE → SAFETY → DEMO → RESULTS → DIFFERENTIATION → IMPACT → FUTURE)

**Slide 1 — Title**
ReconcileAI — Explainable Multi-Source Settlement Reconciliation Agent. Track 04: AI Finance Controller. One line under the title: *"AI investigates. Verification challenges. Policy decides. Audit proves."*

**Slide 2 — Problem**
Quote Track 04's own task text verbatim (`RECONCILEAI_CONTEXT_PACK.md` §2): *"Reconciliation, settlement and forecasting are still done by hand."* One sentence of real pain: fees, timing lag, refunds, duplicates, partial settlements make multi-source records legitimately disagree. Keep this slide to ≤3 lines of text — a problem slide overloaded with detail is the single most common weak opening a judge sees.

**Slide 3 — Why existing approaches fail**
One line per competitor finding from `RECONCILEAI_CONTEXT_PACK.md` §6-8, cited not invented: Razorpay's own Recon is AI-branded with zero disclosed methodology; every competitor detects mismatches but none publicly document investigating root cause with evidence. Do not overcrowd — 3 bullets max, each traceable to the research pack.

**Slide 4 — ReconcileAI (one-line thesis)**
The one-line version from `docs/winning-thesis.md`. This slide should be readable from the back of the room in 2 seconds.

**Slide 5 — Architecture**
The real pipeline diagram (ingest → normalize → match → exception → AI → verify → policy → audit → prioritize → dashboard), taken directly from `docs/final-validation.md` §3. Do not simplify it into something prettier than the real system — the real one is already clean.

**Slide 6 — AI's role (and what it is NOT)**
Two columns: "AI investigates" (root-cause hypothesis for the ~25% residual) vs. "AI never decides" (confidence/recommendation never read by policy). Cite the real number: 74/300 (24.7%) routed to AI. This is the single most important slide for credibility — do not rush it.

**Slide 7 — Safety**
The AI Authority diagram (already built in the product, `frontend/src/components/AiAuthorityDiagram.tsx`) — reuse the actual in-product visual rather than redrawing it, for consistency between deck and demo. State the 0.0000% unsafe auto-resolution rate here, sourced to `docs/final-validation.md` §10.

**Slide 8 — Demo**
A single screenshot of the ₹9.83 golden case's Exception Detail page (real, not mocked up) with an arrow pointing at the contradiction callout. This slide exists to anchor the live demo, not replace it — keep text to a caption only.

**Slide 9 — Results**
The real 300-record distribution (219/67/2/12) and the competitive baseline table from `docs/final-validation.md` §9, re-verified fresh in `docs/final-winning-audit.md` §7 this session. This is a numbers slide — do not decorate it with unrelated icons or animation.

**Slide 10 — Differentiation**
The 5 differentiators from `docs/final-winning-audit.md` §7's "How we are different" list, ranked in the same priority order (financial safety first, innovation-adjacent claims last).

**Slide 11 — Impact / future**
One sentence connecting back to the merchant reconciliation persona (`RECONCILEAI_CONTEXT_PACK.md` §9's "who uses it"). Future work: named honestly from `CLAUDE.md`'s own "Remaining"/"Known limitations" sections (e.g., a real LLM provider exercise, a persisted review workflow) — not invented aspirational features.

**Closing slide**
The one-line winning thesis, repeated verbatim from slide 4. Repetition here is deliberate — it's the line a judge should remember walking out.

## Common weak points to avoid (per this milestone's own instruction to check for them)

- **Overcrowded slides:** every slide above is capped at what fits in 3-5 lines/bullets; if building the actual deck, resist adding "just one more detail" — the docs already hold the detail, the deck should point at it, not contain it.
- **Unsupported claims:** every number named above traces to a specific doc section — do not add a number to the deck that isn't in `docs/final-validation.md`, `docs/final-winning-audit.md`, or a freshly-re-run script output.
- **Missing proof:** slides 6, 7, and 9 are the ones a skeptical judge will scrutinize hardest — each has a named, re-verifiable source above.
- **Weak visuals:** reuse the real product's own AI-authority diagram and a real screenshot rather than redrawing a simplified version that could drift from what the demo actually shows.
- **Unnecessary technical detail:** the architecture slide (5) is the only one that should show internal module names; every other slide should stay in plain language.
- **Weak opening/closing:** the opening (slide 2) and closing (final slide) are both deliberately short and quotable — see `docs/winning-thesis.md` for the exact lines to use.
- **Judge confusion points:** the AI-role slide (6) exists specifically to preempt the most likely judge confusion ("is this really AI or just engineering with an AI label on it?") before it's asked live.
