// A plain, dependency-free horizontal bar chart. Answers one specific
// finance question (Phase 6: "which exception categories dominate?") -- not
// included merely because dashboards usually have charts. Renders as a
// table-like list so screen readers get real text, with a CSS bar drawn
// alongside for at-a-glance scanning.
import { titleCase } from "../lib/format";

export interface BarChartDatum {
  label: string;
  value: number;
}

export function BarChart({ data, caption }: { data: BarChartDatum[]; caption: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));

  if (data.length === 0) {
    return <p className="muted">No data to chart.</p>;
  }

  return (
    <table className="bar-chart">
      <caption className="sr-only">{caption}</caption>
      <tbody>
        {data.map((d) => (
          <tr key={d.label}>
            <th scope="row" className="bar-chart__label">
              {titleCase(d.label)}
            </th>
            <td className="bar-chart__track">
              <div className="bar-chart__bar" style={{ width: `${(d.value / max) * 100}%` }} />
            </td>
            <td className="bar-chart__value">{d.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
