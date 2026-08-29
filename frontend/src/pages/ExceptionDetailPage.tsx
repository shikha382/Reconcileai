// The central investigation experience (Phase 9). Combines three real,
// already-computed API responses -- GET /exceptions/{id} (M8),
// /explanation (M10), /provenance (M6) -- into one evidence-first view.
// This page performs no matching/verification/policy/audit logic of its
// own; every fact shown is read directly from one of those three responses.
import { Link, useLocation, useParams } from "react-router-dom";
import { api } from "../api/client";
import { AiAuthorityDiagram } from "../components/AiAuthorityDiagram";
import { AiHypothesisContradiction, ContradictionItemRow } from "../components/ContradictionCallout";
import { CalculationRow, EvidenceItemRow } from "../components/EvidenceRow";
import { DecisionBadge, PriorityBadge, RiskBadge, SlaBadge, VerdictBadge } from "../components/Badges";
import { ProvenanceTimeline } from "../components/ProvenanceTimeline";
import { ErrorState, LoadingState } from "../components/StatusStates";
import { formatInr, titleCase } from "../lib/format";
import { useApi } from "../lib/useApi";
import type { PrioritizedException } from "../api/types";

export function ExceptionDetailPage() {
  const { exceptionId = "" } = useParams();
  const location = useLocation();
  const priorityFromNav = (location.state as { priorityItem?: PrioritizedException } | null)?.priorityItem;

  const dossierState = useApi(
    () =>
      Promise.all([api.getException(exceptionId), api.getExceptionExplanation(exceptionId), api.getExceptionProvenance(exceptionId)]).then(
        ([detail, explanation, provenance]) => ({ detail, explanation, provenance }),
      ),
    [exceptionId],
  );

  if (dossierState.status === "loading") return <LoadingState label="Loading exception" />;
  if (dossierState.status === "error") return <ErrorState error={dossierState.error} onRetry={dossierState.reload} />;

  const { detail, explanation, provenance } = dossierState.data;
  const priority = explanation.priority ?? (priorityFromNav
    ? { priority: priorityFromNav.priority, priority_score: priorityFromNav.priority_score, reason_codes: priorityFromNav.reason_codes, recommended_action: priorityFromNav.recommended_action }
    : null);

  return (
    <div className="page exception-detail">
      <p>
        <Link to="/work-queue">← Back to Work Queue</Link>
      </p>

      <header className="exception-detail__header">
        <div>
          <h1>{detail.exception_id}</h1>
          <p className="muted">
            Order {detail.order_id} · Payment {detail.payment_id}
          </p>
        </div>
        <div className="exception-detail__header-badges">
          {priority && <PriorityBadge priority={priority.priority} />}
          <RiskBadge level={detail.risk_level} />
          {priorityFromNav && <SlaBadge status={priorityFromNav.sla_status} />}
          <DecisionBadge decision={detail.decision} />
        </div>
      </header>

      <AiAuthorityDiagram compact />

      <div className="exception-detail__summary-grid">
        <div>
          <span className="label">Category</span>
          <span>{titleCase(detail.category)}</span>
        </div>
        <div>
          <span className="label">Reconciliation Status</span>
          <span>{titleCase(detail.reconciliation_status)}</span>
        </div>
        <div>
          <span className="label">Financial Exposure</span>
          <span>{formatInr(detail.financial_exposure)}</span>
        </div>
        <div>
          <span className="label">Risk Score</span>
          <span>{detail.risk_score}</span>
        </div>
      </div>

      {priority && (
        <section className="card priority-explainer" aria-label="Why this exception is prioritized">
          <h2>Why This Exception Is Prioritized</h2>
          <p className="priority-explainer__headline">
            <PriorityBadge priority={priority.priority} /> — {formatInr(detail.financial_exposure)} exposure
          </p>
          <h3>Reasons</h3>
          <ul className="reason-list reason-list--large">
            {priority.reason_codes.map((code) => (
              <li key={code}>{titleCase(code)}</li>
            ))}
          </ul>
          <h3>Recommended Action</h3>
          <p>{titleCase(priority.recommended_action)}</p>
        </section>
      )}

      <section className="card" aria-label="Financial summary">
        <h2>Financial Summary</h2>
        <div className="financial-grid">
          <div>
            <span className="label">Gross Amount</span>
            <span>{formatInr(explanation.financial_summary.gross_amount)}</span>
          </div>
          <div>
            <span className="label">Expected Amount</span>
            <span>{formatInr(explanation.financial_summary.expected_amount)}</span>
          </div>
          <div>
            <span className="label">Observed Amount</span>
            <span>{formatInr(explanation.financial_summary.observed_amount)}</span>
          </div>
          <div>
            <span className="label">Explained Amount</span>
            <span>{formatInr(explanation.financial_summary.explained_amount)}</span>
          </div>
          <div>
            <span className="label">Unexplained Residual</span>
            <span>{formatInr(explanation.financial_summary.unexplained_amount)}</span>
          </div>
        </div>
      </section>

      <section className="card" aria-label="Source records">
        <h2>Source Records</h2>
        <dl className="kv-list">
          <div>
            <dt>Payment</dt>
            <dd>{explanation.source_records.payment_id}</dd>
          </div>
          <div>
            <dt>Order</dt>
            <dd>{explanation.source_records.order_id}</dd>
          </div>
          <div>
            <dt>Settlements</dt>
            <dd>{explanation.source_records.settlement_ids.join(", ") || "—"}</dd>
          </div>
          <div>
            <dt>Bank Transactions</dt>
            <dd>{explanation.source_records.bank_transaction_ids.join(", ") || "—"}</dd>
          </div>
          <div>
            <dt>Refunds</dt>
            <dd>{explanation.source_records.refund_ids.join(", ") || "—"}</dd>
          </div>
        </dl>
      </section>

      <section className="card" aria-label="Evidence">
        <h2>Evidence</h2>
        {explanation.calculation_evidence.length === 0 ? (
          <p className="muted">No calculation-level evidence was recorded for this exception.</p>
        ) : (
          explanation.calculation_evidence.map((trace, i) => <CalculationRow key={i} trace={trace} />)
        )}

        {explanation.matching_evidence.candidates.map((candidate) => (
          <div key={candidate.settlement_id} className="candidate-block">
            <h3>
              Settlement {candidate.settlement_id} — <VerdictBadge verdict={candidate.verdict} /> (score {candidate.score})
            </h3>
            {candidate.positive_evidence.map((item, i) => (
              <EvidenceItemRow key={`pos-${i}`} item={item} />
            ))}
            {candidate.negative_evidence.map((item, i) => (
              <EvidenceItemRow key={`neg-${i}`} item={item} />
            ))}
          </div>
        ))}
      </section>

      <section className="card decision-flow" aria-label="AI investigation and verification">
        <h2>AI Investigation</h2>
        <p className="decision-flow__caption">AI investigates. It does not decide — every hypothesis below is checked deterministically before anything is trusted.</p>
        {explanation.ai_hypotheses.length === 0 ? (
          <p className="muted">This exception did not require AI investigation.</p>
        ) : (
          explanation.ai_hypotheses.map((h) => (
            <div key={h.hypothesis_id} className="hypothesis-block">
              <p className="hypothesis-block__claim">
                <strong>{titleCase(h.hypothesis_type)}:</strong> &ldquo;{h.claim}&rdquo;
              </p>
              <p className="muted">AI confidence (advisory only, never authoritative): {Math.round(h.ai_confidence * 100)}%</p>
              <div className="decision-flow__arrow" aria-hidden="true">
                ↓
              </div>
              <p>
                <strong>Deterministic verification:</strong> <VerdictBadge verdict={h.verification_result} /> — {h.verification_reason}
              </p>
              <AiHypothesisContradiction hypothesis={h} />
            </div>
          ))
        )}

        {explanation.self_challenge.length > 0 && (
          <>
            <h3>Self-Challenge</h3>
            {explanation.self_challenge.map((c, i) => (
              <div key={i} className="hypothesis-block">
                <p>{c.challenge_question}</p>
                <p>
                  <VerdictBadge verdict={c.verification_result} /> — {c.final_result}
                </p>
              </div>
            ))}
          </>
        )}
      </section>

      {explanation.contradictions.length > 0 && (
        <section className="card" aria-label="Contradictions">
          <h2>Contradictions</h2>
          {explanation.contradictions.map((c, i) => (
            <ContradictionItemRow key={i} item={c} />
          ))}
        </section>
      )}

      <section className="card decision-flow" aria-label="Policy and final decision">
        <h2>Policy</h2>
        <p>
          Policy {explanation.policy.policy_id} (v{explanation.policy.policy_version}) evaluated {explanation.policy.rules_evaluated.length} rule(s).
        </p>
        {explanation.policy.reasons.length > 0 && (
          <>
            <h4>Reasons</h4>
            <ul>
              {explanation.policy.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </>
        )}
        {explanation.policy.blocked_reasons.length > 0 && (
          <>
            <h4>Blocked Reasons</h4>
            <ul>
              {explanation.policy.blocked_reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </>
        )}

        <div className="decision-flow__arrow" aria-hidden="true">
          ↓
        </div>

        <h2>Final Decision</h2>
        <p className="decision-flow__final">
          <DecisionBadge decision={detail.decision} />
        </p>
        {detail.review && (
          <p>
            Review <strong>{detail.review.review_id}</strong> — state {titleCase(detail.review.state)}
            {detail.review.dual_control_required ? ", dual control required" : ""}. This exception requires human sign-off; the
            interface does not offer a way to force-approve or bypass this.
          </p>
        )}
        <p className="muted">Financial impact of this decision: {formatInr(explanation.resolution.financial_impact)}</p>
      </section>

      {explanation.missing_evidence.length > 0 && (
        <section className="card" aria-label="Missing evidence">
          <h2>Missing Evidence</h2>
          {explanation.missing_evidence.map((m, i) => (
            <div key={i} className="evidence-item evidence-item--medium">
              <p>
                <strong>{m.required}</strong> — {m.impact}
              </p>
              <p className="muted">Influence on decision: {m.resulting_decision_influence}</p>
            </div>
          ))}
        </section>
      )}

      <section className="card" aria-label="Audit and provenance">
        <h2>Audit &amp; Provenance</h2>
        <p>
          Audit chain: <strong>{provenance.audit_chain_valid ? "Valid" : "INVALID"}</strong> ({provenance.audit_events_checked} events checked)
        </p>
        <ProvenanceTimeline timeline={provenance.timeline} />
      </section>

      <section className="card" aria-label="Narrative summary">
        <h2>Summary</h2>
        <p className="narrative-text">{explanation.human_readable}</p>
        <p className="muted">{explanation.confidence_note}</p>
      </section>
    </div>
  );
}
