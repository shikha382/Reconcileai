# Demo Script (5 minutes)

Maps directly to the 13-step flow specified for this project, each step tied to a concrete screen/action so it's buildable, not just narrated.

1. **Upload 300 records** — `/upload`, select the three-to-four synthetic source files.
2. **Process entire batch** — trigger the pipeline; show it actually running (not a pre-baked result).
3. **Show reconciliation statistics** — `/dashboard`: match rate, counts by decision type (auto-resolved / human review / unresolved).
4. **Show normal automatic matches** — a quick pass over the exact/normalized-match majority, deliberately brief (this is not the interesting part).
5. **Open a difficult exception** — `/exceptions/:id` for a fee-mismatch or split-settlement case.
6. **Show cross-source evidence** — the Evidence panel: which tools were called, what they returned.
7. **Show AI root-cause hypothesis** — the `AIHypothesis` explanation, plainly labeled as a proposal, not a fact.
8. **Show deterministic mathematical verification** — the exact `Decimal` check that either confirms or refutes the hypothesis's math.
9. **Show confidence** — the signal breakdown (reference similarity, amount consistency, date proximity, etc.), not a bare number.
10. **Show "Why NOT Matched"** for a rejected candidate on the same exception — the structured rejection reasons.
11. **Show one intentionally unsafe AI proposal being blocked** — the pre-built adversarial case (see below): the agent proposes something plausible, verification/policy blocks it, and the UI explains why in plain language. **This is the designated wow moment.**
12. **Show financial exposure dashboard** — the Value-at-Risk view: total ₹ exposure across unresolved exceptions, ranked by priority.
13. **Show complete audit trail** — `/audit`: the hash-chained log for everything just shown, including the blocked proposal.

## The wow moment, specifically

The synthetic dataset (`docs/evaluation.md`) includes at least one **adversarial case** purpose-built so that:
- The AI's evidence-gathering surfaces a plausible-looking near match (right amount, close date, similar reference).
- The AI proposes `auto_resolve` with a superficially reasonable explanation.
- The deterministic verification step recomputes the actual arithmetic/relationship and finds it does **not** hold (e.g., the fee math doesn't balance, or there's a conflicting refund on record).
- The policy engine blocks the resolution and routes it to `human_review` (or `blocked`), and the UI states the specific reason — not a generic "error," but "settlement balance check fails: expected ₹4,970, evidence shows ₹4,940, difference unexplained by any fee rule."

This is the single most important scene in the demo: it's the concrete proof that "AI proposes, deterministic logic verifies, policy decides" isn't just a slogan.

## What to explicitly say out loud during the demo

- Name the deterministic/AI/policy/audit boundary at least once, plainly, so a judge doesn't have to infer it.
- State the match rate and the honest unresolved count together — never show one without the other.
- When showing the blocked proposal, say explicitly: "the AI was wrong here, and the system caught it before anything was marked reconciled."
