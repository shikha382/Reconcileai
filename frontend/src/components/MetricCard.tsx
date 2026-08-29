export function MetricCard({
  label,
  value,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: string | number;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
  hint?: string;
}) {
  return (
    <div className={`metric-card metric-card--${tone}`}>
      <span className="metric-card__label">{label}</span>
      <span className="metric-card__value">{value}</span>
      {hint && <span className="metric-card__hint">{hint}</span>}
    </div>
  );
}
