import { api } from "../api";
import type { GapResponse, Inventory } from "../types";
import { PriorityBadge } from "./ConfidenceBadge";

interface Props {
  inventory: Inventory | null;
  onDone: (resp: GapResponse) => void;
  result: GapResponse | null;
  busy: boolean;
  setBusy: (b: boolean) => void;
  setError: (e: string | null) => void;
}

export function GapStep({ inventory, onDone, result, busy, setBusy, setError }: Props) {
  async function run() {
    if (!inventory) return;
    setError(null);
    setBusy(true);
    try {
      onDone(await api.gaps(inventory));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={`card ${inventory ? "" : "disabled"}`}>
      <h2>2 · Map use cases &amp; find gaps</h2>
      <p className="muted">
        Maps the default automation use cases (data/use_cases.json) onto the discovered
        systems, traces data flows, and prioritizes the missing integrations.
      </p>
      <button onClick={run} disabled={busy || !inventory}>
        {busy ? "Analyzing…" : "Analyze integration gaps"}
      </button>

      {result && (
        <div className="result">
          <div className="summary">{result.report.summary}</div>

          <table>
            <thead>
              <tr>
                <th>Priority</th>
                <th>Integration</th>
                <th>Status</th>
                <th>Effort</th>
                <th>Impact</th>
                <th>Blocks</th>
              </tr>
            </thead>
            <tbody>
              {result.report.gaps.map((g) => (
                <tr key={g.id}>
                  <td>
                    <PriorityBadge priority={g.priority} />
                  </td>
                  <td>
                    <b>{g.integration_name}</b>
                    <div className="muted small">{g.description}</div>
                  </td>
                  <td>
                    <span className={g.status === "missing" ? "ground-no" : "ground-ok"}>
                      {g.status}
                    </span>
                  </td>
                  <td>
                    {g.effort_level} ~{g.effort_days}d
                  </td>
                  <td>{g.business_impact_score}</td>
                  <td>{g.blocks_use_cases.length}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {result.report.dependency_statements.length > 0 && (
            <div className="deps">
              <h4>Dependencies</h4>
              <ul>
                {result.report.dependency_statements.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
