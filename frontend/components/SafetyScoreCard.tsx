import type { RiskLevel } from "@/lib/api/types";

/**
 * The deterministic score, set as the lead of the Safety summary: the number
 * itself, its recorded risk level, and a slim meter drawn from that same
 * number. Nothing here is computed — the meter only visualises the reported
 * score against the scale it is already reported on.
 *
 * Risk colour lives here — on the finding surface — and never on the patient
 * identity surface, which stays constant for every patient.
 */
const riskTone: Record<RiskLevel, { surface: string; ink: string }> = {
  high: { surface: "var(--severe-bg)", ink: "var(--severe-fg)" },
  moderate: { surface: "var(--moderate-bg)", ink: "var(--moderate-fg)" },
  low: { surface: "var(--mild-bg)", ink: "var(--mild-fg)" },
};

export function SafetyScoreCard({
  safetyScore,
  riskLevel,
}: {
  safetyScore: number | null;
  riskLevel: RiskLevel | null;
}) {
  const risk = riskLevel ?? null;
  const tone = risk ? riskTone[risk] : { surface: "var(--surface-2)", ink: "var(--ink-2)" };

  return (
    <section aria-label="Safety score" className="pv-safety-score">
      <div className="pv-safety-score-head">
        <p className="pv-safety-score-label">Safety score</p>
        {risk ? (
          <span className="pv-safety-risk" style={{ backgroundColor: tone.surface, color: tone.ink }}>
            {risk} risk
          </span>
        ) : null}
      </div>

      <p className="pv-safety-score-value">
        <span
          className="pv-safety-score-number"
          style={{ color: safetyScore === null ? "var(--ink-3)" : undefined }}
        >
          {safetyScore === null ? "—" : safetyScore}
        </span>
        <span className="pv-safety-score-scale">
          {safetyScore === null ? "Not recorded" : "of 100"}
        </span>
      </p>

      {safetyScore === null ? null : (
        <div className="pv-safety-meter" aria-hidden="true">
          {/* Bounded only so an out-of-range value cannot break the layout. */}
          <span style={{ width: `${Math.min(Math.max(safetyScore, 0), 100)}%`, backgroundColor: tone.ink }} />
        </div>
      )}
    </section>
  );
}
