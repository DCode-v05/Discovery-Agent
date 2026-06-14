import { useRef, useState } from "react";
import { api } from "../api";
import type { DiscoveryResponse, System } from "../types";
import { ConfidenceBadge } from "./ConfidenceBadge";

interface Props {
  onDone: (resp: DiscoveryResponse) => void;
  result: DiscoveryResponse | null;
  busy: boolean;
  setBusy: (b: boolean) => void;
  setError: (e: string | null) => void;
}

export function DiscoveryStep({ onDone, result, busy, setBusy, setError }: Props) {
  const [path, setPath] = useState("data/kb");
  const [fileCount, setFileCount] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);

  async function run() {
    setError(null);
    const files = fileRef.current?.files;
    const hasFiles = !!files && files.length > 0;
    if (!hasFiles && !path.trim()) {
      setError("Choose one or more files to upload, or enter a server-side path (e.g. data/kb).");
      return;
    }
    setBusy(true);
    try {
      const resp = hasFiles
        ? await api.discoverFiles(files!)
        : await api.discoverPath(path.trim());
      onDone(resp);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>1 · Discover systems</h2>
      <p className="muted">
        Point the agent at a folder of mixed documents, or upload your own (PDF, image,
        spreadsheet, Markdown, text). Uploaded files take priority over the path.
      </p>
      <div className="row">
        <label className="grow">
          Server path
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            disabled={busy || fileCount > 0}
            placeholder="data/kb"
          />
        </label>
        <button onClick={run} disabled={busy}>
          {busy ? "Discovering…" : "Discover systems"}
        </button>
      </div>
      <div className="row">
        <input
          type="file"
          multiple
          ref={fileRef}
          disabled={busy}
          onChange={() => setFileCount(fileRef.current?.files?.length ?? 0)}
        />
        <span className="muted small">
          {fileCount > 0
            ? `${fileCount} file${fileCount > 1 ? "s" : ""} selected — using these instead of the path`
            : "or upload your own documents"}
        </span>
      </div>

      {result && <InventoryView systems={result.inventory.systems} resp={result} />}
    </section>
  );
}

function InventoryView({ systems, resp }: { systems: System[]; resp: DiscoveryResponse }) {
  const inv = resp.inventory;
  const reviewing = systems.filter((s) => s.needs_review).length;
  return (
    <div className="result">
      <div className="summary">
        <b>{inv.systems_count}</b> systems from <b>{inv.document_count}</b> documents ·{" "}
        <b>{reviewing}</b> flagged for review · <b>{inv.skipped_documents.length}</b> skipped
        <span className="runid">run {resp.run_id}</span>
      </div>

      {inv.skipped_documents.length > 0 && (
        <div className="warn-box">
          {inv.skipped_documents.map((s) => (
            <div key={s.document}>
              <b>{s.document}</b>: {s.reason} <span className="muted">→ {s.needs}</span>
            </div>
          ))}
        </div>
      )}

      <table>
        <thead>
          <tr>
            <th>System</th>
            <th>Category</th>
            <th>Confidence</th>
            <th>Criticality</th>
            <th>Auth</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {systems.map((s) => (
            <tr key={s.name} className={s.needs_review ? "review-row" : ""}>
              <td>
                <b>{s.name}</b>
                {s.needs_review && <span className="flag">review</span>}
              </td>
              <td>{s.category}</td>
              <td>
                <ConfidenceBadge confidence={s.confidence} tier={s.confidence_tier} />
              </td>
              <td>{s.criticality}</td>
              <td>{s.auth_method}</td>
              <td>
                <details>
                  <summary>{s.evidence.length} cited</summary>
                  {s.uncertainty_note && <p className="note">⚠ {s.uncertainty_note}</p>}
                  <ul>
                    {s.evidence.map((e, i) => (
                      <li key={i}>
                        <span className={e.grounded ? "ground-ok" : "ground-no"}>
                          {e.grounded ? "✓" : "✗"}
                        </span>{" "}
                        “{e.quote.slice(0, 140)}” <span className="muted">— {e.source_doc} ({e.location})</span>
                      </li>
                    ))}
                  </ul>
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
