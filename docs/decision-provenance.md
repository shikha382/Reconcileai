# Decision Provenance

Given only an `exception_id` and the audit ledger, reconstruct the full story of one decision — no business logic is ever recomputed to answer this; every field comes straight off recorded audit events. A future dashboard renders this directly.

## The one shared correlation_id

`app.services.decision_service.run_decision_pipeline` is the single M6 orchestrator for one exception. It generates one `correlation_id` (`CORR-{12 hex chars}`) at the very start and threads it through every audit event the whole pipeline emits — `EXCEPTION_CREATED`, optionally `AI_INVESTIGATION_STARTED`/`AI_INVESTIGATION_COMPLETED`, per-hypothesis `HYPOTHESIS_CREATED`/`HYPOTHESIS_CHALLENGED`/`CONTRADICTION_FOUND`/`HYPOTHESIS_REJECTED`/`HYPOTHESIS_VERIFIED`, `POLICY_EVALUATED`, `RESOLUTION_PROPOSED`, and (when required) `REVIEW_REQUESTED`. `AuditLedger.events_for_correlation(correlation_id)` returns exactly this set, in order.

## `get_decision_provenance(session, exception_id)`

`backend/app/audit/provenance.py`. Looks up every audit event for that `exception_id` (`events_for_entity`, indexed), and reconstructs:

- `timeline` — every event, in order, as `{timestamp, event_type, actor_type, actor_id, payload}`
- `ai_hypotheses` — the payload of every `HYPOTHESIS_CREATED` event
- `contradictions` — the payload of every `HYPOTHESIS_CHALLENGED`/`CONTRADICTION_FOUND` event (structured `ContradictionRecord.to_dict()` shapes — see `docs/contradiction-evidence.md`)
- `policy_evaluation` — the single `POLICY_EVALUATED` event's payload (the `PolicyDecision.to_dict()` shape)
- `resolution_proposal` — the single `RESOLUTION_PROPOSED` event's payload
- `review` — the `REVIEW_REQUESTED` event's payload, if one exists
- `audit_chain_valid` / `audit_events_checked` — the result of running `verify_chain(session)` at the moment of the call (see `docs/audit-ledger.md`'s performance note on why this is a full-ledger check, not a per-entity one)

A record with no matching events (an unknown `exception_id`) returns an empty-but-well-shaped `DecisionProvenance` — `timeline=[]`, `correlation_id=None`, everything else `None`/`[]` — never an exception or a `None` return.

## `build_decision_summary(provenance)`

Phase 14's one structured answer to every question a reviewer or a future UI would ask about a decision:

```json
{
  "exception_id": "...",
  "ai_believed": ["<hypothesis claim text, per tested hypothesis>"],
  "supporting_evidence": ["<evidence_ids where a hypothesis was SUPPORTED>"],
  "contradicting_evidence": ["<evidence_ids where a hypothesis was CONTRADICTED>"],
  "verification_conclusion": "CONTRADICTED | VERIFIED | NOT_NEEDED",
  "policy_decision": "SAFE_TO_RESOLVE | HUMAN_REVIEW | REJECTED | ESCALATED | UNRESOLVED",
  "policy_id": "RECONCILEAI-CORE-POLICY",
  "policy_version": "1.0.0",
  "financial_exposure": "<Decimal-as-string>",
  "approval_required": true,
  "review_id": "REV-... or null",
  "audit_chain_valid": true,
  "audit_events_checked": 1234
}
```

`verification_conclusion` is `"CONTRADICTED"` if any tested hypothesis was contradicted, `"VERIFIED"` if hypotheses were tested and none were contradicted, `"NOT_NEEDED"` if the exception never needed AI investigation at all (M3's root cause was already conclusive).

## Immutable decision snapshot (Phase 8)

Every fact a reviewer needs to trust a decision is captured **as it was at decision time**, inside the audit events themselves — never recomputed later from current code/config, which could silently drift:

- **Policy**: `policy_id`, `policy_version`, `rules_evaluated`/`rules_passed`/`rules_failed`, `input_hash` (`POLICY_EVALUATED` payload — `PolicyDecision.to_dict()`)
- **Verifier**: `expected_value`, `observed_value`, `residual`, the constraint/reason string (`HYPOTHESIS_CHALLENGED` payload — `ContradictionRecord.to_dict()`)
- **AI**: `provider`, `model`, `tool_call_count`, `hypotheses_tested`, `duration_seconds` (`AI_INVESTIGATION_COMPLETED` payload); per-hypothesis `hypothesis_type`, `claim`, `confidence` (`HYPOTHESIS_CREATED` payload — audit-only, never authoritative, see `docs/contradiction-evidence.md`)
- **Risk**: financial exposure and resolution details (`RESOLUTION_PROPOSED` payload — `ResolutionProposal.to_dict()`, includes `financial_impact`)

No secrets, no raw model prompt/chain-of-thought is ever stored — only the structured, already-validated outputs each stage of the pipeline produced.

## What this is not

Provenance reconstruction never re-runs the reconciliation, exception-intelligence, AI investigation, or policy engine to "check" a past decision. It only reads back what was recorded when the decision was made. If the underlying code changes tomorrow, yesterday's provenance still reports yesterday's actual inputs and outputs — that is the point of an audit trail.
