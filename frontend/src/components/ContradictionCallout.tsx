// Phase 13: contradictions are one of the project's strongest differentiator
// moments -- rendered as a dedicated, visually distinct callout, never
// buried inside a generic paragraph.
import type { AIHypothesisTrace, ContradictionItem } from "../api/types";

export function AiHypothesisContradiction({ hypothesis }: { hypothesis: AIHypothesisTrace }) {
  const contradicted = hypothesis.verification_result === "CONTRADICTED" || hypothesis.final_disposition === "REJECTED";
  if (!contradicted) return null;

  return (
    <div className="contradiction-callout" role="alert">
      <p className="contradiction-callout__title">
        <span aria-hidden="true">⚠</span> CONTRADICTION DETECTED
      </p>
      <dl className="contradiction-callout__body">
        <dt>AI hypothesis</dt>
        <dd>&ldquo;{hypothesis.claim}&rdquo;</dd>
        <dt>Verification</dt>
        <dd>Rejected</dd>
        <dt>Reason</dt>
        <dd>{hypothesis.verification_reason}</dd>
        <dt>Disposition</dt>
        <dd>{hypothesis.final_disposition}</dd>
      </dl>
    </div>
  );
}

export function ContradictionItemRow({ item }: { item: ContradictionItem }) {
  return (
    <div className="contradiction-callout" role="alert">
      <p className="contradiction-callout__title">
        <span aria-hidden="true">⚠</span> {item.field}
      </p>
      <dl className="contradiction-callout__body">
        <dt>Expected ({item.source_a})</dt>
        <dd>{item.expected ?? "—"}</dd>
        <dt>Observed ({item.source_b})</dt>
        <dd>{item.observed ?? "—"}</dd>
        <dt>Impact</dt>
        <dd>{item.impact}</dd>
      </dl>
    </div>
  );
}
