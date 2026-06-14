import { useEffect, useState } from "react";
import { api } from "../api";
import type { Ledger, RunEvent } from "../types";

const LEVEL_CLASS: Record<string, string> = {
  error: "ev-error",
  warning: "ev-warn",
  info: "ev-info",
};

const KEY_EVENTS = new Set([
  "decision",
  "llm_call",
  "confidence",
  "failure",
  "grounding_failed",
  "grounding_unverifiable",
  "artifact_validated",
  "run_finished",
]);

export function Observability({ runId }: { runId: string | null }) {
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [filter, setFilter] = useState(true);

  useEffect(() => {
    if (!runId) return;
    let active = true;
    api
      .run(runId)
      .then((l) => active && setLedger(l))
      .catch(() => active && setLedger(null));
    return () => {
      active = false;
    };
  }, [runId]);

  if (!runId) return <p className="muted">Run a step to see the agent's reasoning trace.</p>;
  if (!ledger) return <p className="muted">Loading trace…</p>;

  const events = filter ? ledger.events.filter((e) => KEY_EVENTS.has(e.event)) : ledger.events;

  return (
    <div className="obs">
      <div className="obs-head">
        <span>
          <b>{ledger.kind}</b> · {ledger.events.length} events · run {ledger.run_id}
        </span>
        <label className="muted">
          <input type="checkbox" checked={filter} onChange={(e) => setFilter(e.target.checked)} />{" "}
          key events only
        </label>
      </div>
      <ol className="timeline">
        {events.map((e, i) => (
          <li key={i} className={LEVEL_CLASS[e.level] ?? "ev-info"}>
            <code>{e.event}</code> {summarize(e)}
          </li>
        ))}
      </ol>
    </div>
  );
}

function summarize(e: RunEvent): string {
  switch (e.event) {
    case "decision":
      return `${e.what} → ${e.choice} (${e.why})`;
    case "llm_call":
      return `${e.provider}/${e.model} · ${e.task} · ${e.latency_ms}ms${e.tokens ? ` · ${e.tokens} tok` : ""}`;
    case "confidence":
      return `${e.subject}: ${Math.round(Number(e.score) * 100)}% (${e.tier})`;
    case "failure":
      return `${e.what}: ${e.error} → needs: ${e.needs}`;
    case "artifact_validated":
      return `${e.package}: syntax=${e.syntax} import=${e.import_ok} yaml=${e.yaml_ok} tests=${e.tests_pass}`;
    case "grounding_failed":
    case "grounding_unverifiable":
      return `${e.system}: ${e.why}`;
    case "run_finished":
      return Object.entries(e)
        .filter(([k]) => !["run_id", "ts", "event", "level"].includes(k))
        .map(([k, v]) => `${k}=${v}`)
        .join(" · ");
    default:
      return "";
  }
}
