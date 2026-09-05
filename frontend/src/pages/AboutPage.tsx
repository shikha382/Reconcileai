// Milestone 15: a compact "why is this different" page (Phases 11-14).
// Everything here is either a live link to a real page (Data Sources) or
// static content citing a specific, already-measured result (the M13
// competitive evaluation) -- never a live per-run metric presented as if
// it were static, and never a number invented for this page.
import { Link } from "react-router-dom";
import { AiAuthorityDiagram } from "../components/AiAuthorityDiagram";
import { PageHeader } from "../components/PageHeader";

const PIPELINE_STAGES = [
  "Sources", "Provider Adapters", "Validation + Normalization", "Deterministic Reconciliation",
  "Exception Intelligence", "AI Investigation", "Self-Challenge", "Verification", "Risk + Policy",
  "Decision", "Audit + Explanation", "Priority Queue", "API", "Controller Dashboard",
];

export function AboutPage() {
  return (
    <div className="page">
      <PageHeader
        eyebrow="Product thesis"
        title="Why ReconcileAI Is Different"
        description="AI investigates financial exceptions; independent verification and deterministic policy retain decision authority."
      />

      <section className="card" aria-label="AI is not the decision authority">
        <h2>AI Proposes. Policy Decides. Audit Remembers.</h2>
        <AiAuthorityDiagram />
        <p className="muted">
          The AI never gains unilateral financial authority — it only ever investigates. Every hypothesis is
          independently re-derived with Decimal-exact arithmetic, and the policy engine is the sole authority that sets
          the final decision.
        </p>
      </section>

      <section className="card" aria-label="Competitive differentiation">
        <h2>Competitive Differentiation</h2>
        <p className="muted">
          Measured directly against the real 300-record dataset, Milestone 13 (<code>scripts/evaluate_competitive_baselines.py</code>) —
          see <code>docs/demo-runbook.md</code> for the full methodology. Not re-measured live on this page; these are
          fixed, cited historical evaluation results.
        </p>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Approach</th>
                <th>Precision</th>
                <th>Recall</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Exact-ID matching only</td>
                <td className="num">1.00</td>
                <td className="num">0.89</td>
                <td>Misses noisy/reformatted references entirely</td>
              </tr>
              <tr>
                <td>Amount-only matching</td>
                <td className="num">0.96</td>
                <td className="num">0.83</td>
                <td>10 false matches from amount collisions</td>
              </tr>
              <tr>
                <td>Naive fuzzy matching, no verification gate</td>
                <td className="num">—</td>
                <td className="num">—</td>
                <td>
                  <strong className="text-danger">14.67% unsafe auto-resolution rate</strong>
                </td>
              </tr>
              <tr>
                <td>Mock-AI direct-trust proxy</td>
                <td className="num">—</td>
                <td className="num">—</td>
                <td>0 direct auto-resolve recommendations; no measured lift or unsafe rate</td>
              </tr>
              <tr>
                <td>
                  <strong>ReconcileAI</strong>
                </td>
                <td className="num">
                  <strong>1.0000</strong>
                </td>
                <td className="num">
                  <strong>1.0000</strong>
                </td>
                <td>
                  <strong className="text-success">0.0000% unsafe auto-resolution rate</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="card" aria-label="Architecture">
        <h2>Architecture</h2>
        <ol className="stage-list">
          {PIPELINE_STAGES.map((stage) => (
            <li key={stage}>{stage}</li>
          ))}
        </ol>
        <p className="muted">
          <strong>AI</strong> is the investigation layer only. <strong>Policy</strong> is the sole decision authority.{" "}
          <strong>Audit</strong> is the tamper-evident evidence/provenance layer. See <code>docs/architecture.md</code> for the full
          per-milestone breakdown.
        </p>
      </section>

      <section className="card" aria-label="Security story">
        <h2>Security</h2>
        <ul className="plain-list">
          <li>No financial-record mutation, force-resolve, refund, payout, or approval-bypass endpoint exists.</li>
          <li>The AI actor cannot start a reconciliation run and cannot override a policy decision.</li>
          <li>Every API error uses one structured contract — never a stack trace, a secret, or an internal path.</li>
          <li>No secret (API key, database credential) is ever logged, returned, or sent to the frontend.</li>
          <li>Audit-ledger tampering is detected — 8+ tamper types tested directly.</li>
          <li>Every financial calculation uses Decimal arithmetic — no floating-point money, anywhere.</li>
          <li>125+ adversarial tests (Milestone 9) and a dedicated security audit (Milestone 13) exercise all of the above.</li>
        </ul>
        <p className="muted">See <code>docs/demo-runbook.md</code>'s claim-vs-proof matrix for the exact test backing each line above.</p>
      </section>

      <section className="card" aria-label="Data sources">
        <h2>Data Sources</h2>
        <p>
          Every source used in this demo runs on <strong>synthetic, deterministic data</strong> — reproducible, offline, with known
          ground truth. See the live status of every configured source on{" "}
          <Link to="/health">System Health</Link>.
        </p>
      </section>
    </div>
  );
}
