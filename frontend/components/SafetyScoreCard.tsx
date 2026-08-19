import type { RiskLevel } from "@/lib/api/types";

const riskStyles: Record<RiskLevel, string> = {
  high: "text-high",
  moderate: "text-moderate",
  low: "text-low",
};

const riskRing: Record<RiskLevel, string> = {
  high: "border-high/30 bg-[#fdf2f4]",
  moderate: "border-moderate/30 bg-[#fdf6ec]",
  low: "border-low/30 bg-[#eef7f4]",
};

export function SafetyScoreCard({
  safetyScore,
  riskLevel,
}: {
  safetyScore: number | null;
  riskLevel: RiskLevel | null;
}) {
  const risk = riskLevel ?? null;
  return (
    <section
      aria-label="Safety score"
      className={`rounded-2xl border px-5 py-5 sm:px-8 sm:py-6 ${risk ? riskRing[risk] : "border-line bg-card"}`}
    >
      <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted">
        Deterministic safety score
      </p>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-5xl font-semibold leading-none tracking-tight text-ink sm:text-6xl">
            {safetyScore === null ? "—" : safetyScore}
          </p>
          <p className="mt-2 max-w-sm text-sm text-muted">
            Out of 100. Produced by rule engines, not by the language model.
          </p>
        </div>
        <div className="sm:text-right">
          <p className="text-xs uppercase tracking-[0.14em] text-muted">Risk level</p>
          <p className={`mt-1 text-2xl font-semibold capitalize ${risk ? riskStyles[risk] : "text-ink"}`}>
            {risk ?? "unavailable"}
          </p>
        </div>
      </div>
    </section>
  );
}
