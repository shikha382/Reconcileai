// Milestone 15, Phase 6: the single strongest differentiator, rendered as
// one compact, reusable visual -- AI investigates, evidence/verification
// challenges, policy decides, audit proves. Never implies the AI
// independently guarantees correctness.
export function AiAuthorityDiagram({ compact = false }: { compact?: boolean }) {
  const steps = [
    { label: "AI", action: "INVESTIGATES", detail: "Proposes a hypothesis from real evidence — advisory only." },
    { label: "VERIFICATION", action: "CHALLENGES", detail: "Independently re-derives the arithmetic with Decimal-exact math." },
    { label: "POLICY", action: "DECIDES", detail: "The only authority that sets the final outcome — never the AI." },
    { label: "AUDIT", action: "PROVES", detail: "Every step is recorded on a tamper-evident, hash-chained ledger." },
  ];

  return (
    <div className={`ai-authority-diagram ${compact ? "ai-authority-diagram--compact" : ""}`} role="group" aria-label="AI is not the decision authority">
      {steps.map((step, i) => (
        <div className="ai-authority-diagram__step" key={step.label}>
          <div className="ai-authority-diagram__box">
            <span className="ai-authority-diagram__label">{step.label}</span>
            <span className="ai-authority-diagram__action">{step.action}</span>
            {!compact && <span className="ai-authority-diagram__detail">{step.detail}</span>}
          </div>
          {i < steps.length - 1 && (
            <span className="ai-authority-diagram__arrow" aria-hidden="true">
              →
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
