import type { RiskLevel } from "@/lib/api/types";

/**
 * Risk colour belongs here — on the safety finding surface — and not on the
 * patient identity surface, which stays visually constant for every patient.
 */
const riskTone: Record<RiskLevel, { surface: string; ink: string }> = {
  high: { surface: "var(--severe-surface)", ink: "var(--severe-ink)" },
  moderate: { surface: "var(--moderate-surface)", ink: "var(--moderate-ink)" },
  low: { surface: "var(--mild-surface)", ink: "var(--mild-ink)" },
};

export function SafetyScoreCard({
  safetyScore,
  riskLevel,
}: {
  safetyScore: number | null;
  riskLevel: RiskLevel | null;
}) {
  const risk = riskLevel ?? null;
  const tone = risk ? riskTone[risk] : null;

  return (
    <section
      aria-label="Safety score"
      className="rounded-md px-5 py-5 sm:px-6"
      style={{ backgroundColor: tone ? tone.surface : "var(--surface-sunk)" }}
    >
      <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-ink-3">
        Deterministic safety score
      </p>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[2.75rem] font-semibold leading-none tracking-[-0.03em] text-ink sm:text-[3.25rem]">
            {safetyScore === null ? "—" : safetyScore}
            {safetyScore === null ? null : (
              <span className="ml-1.5 align-baseline text-[0.9375rem] font-medium text-ink-3">
                of 100
              </span>
            )}
          </p>
          <p className="mt-2 max-w-sm text-[0.8125rem] leading-5 text-ink-2">
            Out of 100. Produced by rule engines, not by the language model.
          </p>
        </div>
        <div className="sm:text-right">
          <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-ink-3">
            Risk level
          </p>
          <p
            className="mt-1 text-[1.375rem] font-semibold capitalize"
            style={{ color: tone ? tone.ink : "var(--ink)" }}
          >
            {risk ?? "unavailable"}
          </p>
        </div>
      </div>
    </section>
  );
}
