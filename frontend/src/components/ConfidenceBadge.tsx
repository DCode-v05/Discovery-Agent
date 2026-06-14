interface Props {
  confidence: number;
  tier: string;
}

const TIER_CLASS: Record<string, string> = {
  explicit: "badge-green",
  inferred: "badge-amber",
  review: "badge-red",
};

export function ConfidenceBadge({ confidence, tier }: Props) {
  return (
    <span className={`badge ${TIER_CLASS[tier] ?? "badge-gray"}`} title={`tier: ${tier}`}>
      {Math.round(confidence * 100)}% · {tier}
    </span>
  );
}

export function Pill({ ok, label }: { ok: boolean | null; label: string }) {
  const cls = ok === null ? "badge-gray" : ok ? "badge-green" : "badge-red";
  const mark = ok === null ? "—" : ok ? "✓" : "✗";
  return (
    <span className={`badge ${cls}`}>
      {mark} {label}
    </span>
  );
}

const PRIORITY_CLASS: Record<string, string> = {
  critical: "badge-red",
  high: "badge-amber",
  medium: "badge-blue",
  low: "badge-gray",
};

export function PriorityBadge({ priority }: { priority: string }) {
  return <span className={`badge ${PRIORITY_CLASS[priority] ?? "badge-gray"}`}>{priority}</span>;
}
