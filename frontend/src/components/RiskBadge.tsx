import type { RiskBand } from "../types";

const LABELS: Record<RiskBand, string> = {
  low: "Low",
  "low-medium": "Low-Medium",
  medium: "Medium",
  high: "High",
};

export function RiskBadge({ band }: { band: RiskBand }) {
  return (
    <span className={`risk-badge risk-badge--${band}`}>
      <span className="risk-badge__dot" aria-hidden="true" />
      {LABELS[band]}
    </span>
  );
}
