// Status indicators never rely on color alone (Phase 24) -- each badge pairs
// a color with a distinct symbol AND a text label. Values mirror the
// backend's own closed enums (app.policy.schemas) verbatim; unrecognized
// values still render (as "neutral"), never silently disappear.
const DECISION_META: Record<string, { label: string; symbol: string; tone: string }> = {
  SAFE_TO_RESOLVE: { label: "Auto Resolved", symbol: "✓", tone: "success" },
  HUMAN_REVIEW: { label: "Human Review", symbol: "!", tone: "warning" },
  REJECTED: { label: "Blocked", symbol: "⛔", tone: "danger" },
  ESCALATED: { label: "Escalated", symbol: "▲", tone: "danger" },
  UNRESOLVED: { label: "Unresolved", symbol: "?", tone: "neutral" },
};

export function DecisionBadge({ decision }: { decision: string }) {
  const meta = DECISION_META[decision] ?? { label: decision, symbol: "•", tone: "neutral" };
  return (
    <span className={`badge badge--${meta.tone}`}>
      <span className="badge__symbol" aria-hidden="true">
        {meta.symbol}
      </span>
      {meta.label}
    </span>
  );
}

const RISK_META: Record<string, { symbol: string; tone: string }> = {
  LOW: { symbol: "●", tone: "success" },
  MEDIUM: { symbol: "▲", tone: "warning" },
  HIGH: { symbol: "▲▲", tone: "danger" },
  CRITICAL: { symbol: "▲▲▲", tone: "danger" },
};

export function RiskBadge({ level }: { level: string }) {
  const meta = RISK_META[level] ?? { symbol: "•", tone: "neutral" };
  return (
    <span className={`badge badge--${meta.tone} badge--outline`}>
      <span aria-hidden="true">{meta.symbol}</span> {level}
    </span>
  );
}

const PRIORITY_META: Record<string, { tone: string; description: string }> = {
  P0: { tone: "danger", description: "Critical priority" },
  P1: { tone: "warning", description: "High priority" },
  P2: { tone: "info", description: "Medium priority" },
  P3: { tone: "neutral", description: "Low priority" },
};

export function PriorityBadge({ priority }: { priority: string }) {
  const meta = PRIORITY_META[priority] ?? { tone: "neutral", description: priority };
  return (
    <span className={`badge badge--${meta.tone} badge--priority`} title={meta.description}>
      {priority}
    </span>
  );
}

const SLA_META: Record<string, { label: string; symbol: string; tone: string }> = {
  BREACHED: { label: "SLA Breached", symbol: "⏰", tone: "danger" },
  AT_RISK: { label: "SLA At Risk", symbol: "⏳", tone: "warning" },
  WITHIN_SLA: { label: "Within SLA", symbol: "✓", tone: "success" },
};

export function SlaBadge({ status }: { status: string }) {
  const meta = SLA_META[status] ?? { label: status, symbol: "•", tone: "neutral" };
  return (
    <span className={`badge badge--${meta.tone} badge--outline`}>
      <span aria-hidden="true">{meta.symbol}</span> {meta.label}
    </span>
  );
}

const VERDICT_META: Record<string, { label: string; symbol: string; tone: string }> = {
  CONTRADICTED: { label: "Contradicted", symbol: "⚠", tone: "danger" },
  SUPPORTED: { label: "Supported", symbol: "✓", tone: "success" },
  INSUFFICIENT_EVIDENCE: { label: "Insufficient Evidence", symbol: "?", tone: "neutral" },
  VERIFIED: { label: "Verified", symbol: "✓", tone: "success" },
  NOT_NEEDED: { label: "Not Needed", symbol: "–", tone: "neutral" },
};

export function VerdictBadge({ verdict }: { verdict: string }) {
  const meta = VERDICT_META[verdict] ?? { label: verdict, symbol: "•", tone: "neutral" };
  return (
    <span className={`badge badge--${meta.tone}`}>
      <span className="badge__symbol" aria-hidden="true">
        {meta.symbol}
      </span>
      {meta.label}
    </span>
  );
}
