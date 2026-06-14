import { useState } from "react";
import { api } from "../api";
import type { CodegenResponse, ConnectorArtifact, GapReport } from "../types";
import { Pill } from "./ConfidenceBadge";

interface Props {
  report: GapReport | null;
  onDone: (resp: CodegenResponse) => void;
  result: CodegenResponse | null;
  busy: boolean;
  setBusy: (b: boolean) => void;
  setError: (e: string | null) => void;
}

export function CodegenStep({ report, onDone, result, busy, setBusy, setError }: Props) {
  const [topN, setTopN] = useState(3);

  async function run() {
    if (!report) return;
    setError(null);
    setBusy(true);
    try {
      onDone(await api.codegen(report.gaps, topN));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={`card ${report ? "" : "disabled"}`}>
      <h2>3 · Generate connector code</h2>
      <p className="muted">
        For the top missing integrations, generates a runnable Python connector (auth,
        CRUD, pagination, rate limiting, retries, errors), an agent definition, unit
        tests, and a README — each validated (syntax, import, YAML, and a real pytest run).
      </p>
      <div className="row">
        <label>
          Top N gaps
          <input
            type="number"
            min={1}
            max={6}
            value={topN}
            onChange={(e) => setTopN(Number(e.target.value))}
            disabled={busy}
          />
        </label>
        <button onClick={run} disabled={busy || !report}>
          {busy ? "Generating…" : "Generate code"}
        </button>
        {result?.bundle_url && (
          <a className="download" href={api.bundleHref(result.bundle_url)}>
            ⬇ Download bundle (.zip)
          </a>
        )}
      </div>

      {result?.result.artifacts.map((a) => (
        <ArtifactCard key={a.gap_id} artifact={a} />
      ))}
    </section>
  );
}

function ArtifactCard({ artifact }: { artifact: ConnectorArtifact }) {
  const [selected, setSelected] = useState(artifact.files[0]?.path ?? "");
  if (artifact.error) {
    return (
      <div className="artifact error">
        <b>{artifact.integration_name}</b> — <span className="ground-no">{artifact.error}</span>
      </div>
    );
  }
  const file = artifact.files.find((f) => f.path === selected);
  const v = artifact.validation;
  return (
    <div className="artifact">
      <div className="artifact-head">
        <b>{artifact.system_name}</b> <code>{artifact.package_name}</code>
        <span className="muted">— {artifact.integration_name}</span>
      </div>
      <div className="pills">
        <Pill ok={v.syntax_ok} label="syntax" />
        <Pill ok={v.import_ok} label="imports" />
        <Pill ok={v.yaml_ok} label="yaml" />
        <Pill ok={v.tests_pass} label="pytest" />
      </div>
      {v.issues.length > 0 && <div className="warn-box small">{v.issues.join("; ")}</div>}
      <div className="tabs">
        {artifact.files.map((f) => (
          <button
            key={f.path}
            className={f.path === selected ? "tab active" : "tab"}
            onClick={() => setSelected(f.path)}
          >
            {f.path.split("/").pop()}
          </button>
        ))}
      </div>
      <pre className="code">{file?.content}</pre>
    </div>
  );
}
