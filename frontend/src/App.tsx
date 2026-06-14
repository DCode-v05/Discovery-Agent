import { useEffect, useState } from "react";
import { api } from "./api";
import { CodegenStep } from "./components/CodegenStep";
import { DiscoveryStep } from "./components/DiscoveryStep";
import { GapStep } from "./components/GapStep";
import { Observability } from "./components/Observability";
import type { CodegenResponse, DiscoveryResponse, GapResponse, Health } from "./types";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [discovery, setDiscovery] = useState<DiscoveryResponse | null>(null);
  const [gaps, setGaps] = useState<GapResponse | null>(null);
  const [codegen, setCodegen] = useState<CodegenResponse | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  return (
    <div className="app">
      <header>
        <div>
          <h1>Discovery Agent</h1>
          <p className="tagline">
            Documents → systems inventory → integration gaps → working connector code
          </p>
        </div>
        <div className="providers">
          {health ? (
            <>
              <ProviderDot name="Gemini" ok={health.providers.gemini} />
              <ProviderDot name="Groq" ok={health.providers.groq} />
            </>
          ) : (
            <span className="muted">backend offline</span>
          )}
        </div>
      </header>

      {error && (
        <div className="error-banner">
          <b>Failed:</b> {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      <div className="layout">
        <main>
          <DiscoveryStep
            result={discovery}
            busy={busy}
            setBusy={setBusy}
            setError={setError}
            onDone={(r) => {
              setDiscovery(r);
              setGaps(null);
              setCodegen(null);
              setRunId(r.run_id);
            }}
          />
          <GapStep
            inventory={discovery?.inventory ?? null}
            result={gaps}
            busy={busy}
            setBusy={setBusy}
            setError={setError}
            onDone={(r) => {
              setGaps(r);
              setCodegen(null);
              setRunId(r.run_id);
            }}
          />
          <CodegenStep
            report={gaps?.report ?? null}
            result={codegen}
            busy={busy}
            setBusy={setBusy}
            setError={setError}
            onDone={(r) => {
              setCodegen(r);
              setRunId(r.run_id);
            }}
          />
        </main>

        <aside>
          <h3>Observability</h3>
          <Observability runId={runId} />
        </aside>
      </div>
    </div>
  );
}

function ProviderDot({ name, ok }: { name: string; ok: boolean }) {
  return (
    <span className="provider" title={ok ? "API key configured" : "no API key — set it in .env"}>
      <span className={ok ? "dot dot-on" : "dot dot-off"} /> {name}
    </span>
  );
}
