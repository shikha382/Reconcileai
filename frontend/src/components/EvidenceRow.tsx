// Phase 12 "evidence-first design": every claim is rendered next to its own
// evidence, verification, and result -- never a bare narrative sentence.
import type { CalculationTrace, EvidenceItem } from "../api/types";
import { VerdictBadge } from "./Badges";
import { titleCase } from "../lib/format";

export function CalculationRow({ trace }: { trace: CalculationTrace }) {
  return (
    <div className="evidence-row">
      <div className="evidence-row__claim">
        <span className="evidence-row__kicker">Claim</span>
        <p>{trace.label}</p>
        {trace.rule_id && <p className="muted">Rule: {trace.rule_id}</p>}
      </div>
      <div className="evidence-row__evidence">
        <span className="evidence-row__kicker">Evidence</span>
        {Object.entries(trace.inputs).length === 0 ? (
          <p className="muted">No inputs recorded.</p>
        ) : (
          <dl className="kv-list">
            {Object.entries(trace.inputs).map(([key, value]) => (
              <div key={key}>
                <dt>{titleCase(key)}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
      <div className="evidence-row__verification">
        <span className="evidence-row__kicker">Verification</span>
        {trace.expected_value !== null || trace.observed_value !== null ? (
          <p>
            Expected {trace.expected_value ?? "—"} vs. observed {trace.observed_value ?? "—"}
            {trace.residual !== null && <> — residual {trace.residual}</>}
          </p>
        ) : (
          <p className="muted">No numeric comparison recorded.</p>
        )}
      </div>
      <div className="evidence-row__result">
        <span className="evidence-row__kicker">Result</span>
        <VerdictBadge verdict={trace.verification_result} />
      </div>
    </div>
  );
}

export function EvidenceItemRow({ item }: { item: EvidenceItem }) {
  return (
    <div className={`evidence-item evidence-item--${item.severity.toLowerCase()}`}>
      <div className="evidence-item__head">
        <span className="evidence-item__type">{titleCase(item.evidence_type)}</span>
        <VerdictBadge verdict={item.status} />
      </div>
      <p>{item.explanation}</p>
      {(item.expected_value !== null || item.observed_value !== null) && (
        <p className="muted">
          {item.field ? `${titleCase(item.field)}: ` : ""}
          expected {item.expected_value ?? "—"}, observed {item.observed_value ?? "—"}
        </p>
      )}
      <p className="muted evidence-item__source">
        Source: {titleCase(item.source_type)} {item.source_id}
      </p>
    </div>
  );
}
