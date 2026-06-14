import type {
  CodegenResponse,
  DiscoveryResponse,
  GapResponse,
  Health,
  Inventory,
  IntegrationGap,
  Ledger,
} from "./types";

// Default to the dev proxy (/api -> :8000). Override with VITE_API_BASE.
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* non-JSON error body */
    }
    if (detail && typeof detail === "object" && "error" in detail) {
      const d = detail as { error: string; needs?: string };
      throw new Error(d.needs ? `${d.error} — ${d.needs}` : d.error);
    }
    throw new Error(String(detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  base: BASE,

  health: () => fetch(`${BASE}/health`).then((r) => unwrap<Health>(r)),

  discoverPath: (path: string) => {
    const form = new FormData();
    form.append("path", path);
    return fetch(`${BASE}/discovery/run`, { method: "POST", body: form }).then((r) =>
      unwrap<DiscoveryResponse>(r),
    );
  },

  discoverFiles: (files: FileList) => {
    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));
    return fetch(`${BASE}/discovery/run`, { method: "POST", body: form }).then((r) =>
      unwrap<DiscoveryResponse>(r),
    );
  },

  gaps: (inventory: Inventory) =>
    fetch(`${BASE}/gaps/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inventory }),
    }).then((r) => unwrap<GapResponse>(r)),

  codegen: (gaps: IntegrationGap[], topN: number) =>
    fetch(`${BASE}/codegen/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gaps, top_n: topN, run_tests: true }),
    }).then((r) => unwrap<CodegenResponse>(r)),

  run: (id: string) => fetch(`${BASE}/runs/${id}`).then((r) => unwrap<Ledger>(r)),

  bundleHref: (bundleUrl: string) => `${BASE}${bundleUrl}`,
};
