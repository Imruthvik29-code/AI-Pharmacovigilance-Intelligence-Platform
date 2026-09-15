import type { RiskLevel } from "@/lib/api/types";

/**
 * The deterministic score as the lead of the Safety summary: a ring gauge
 * holding the recorded number, with the recorded risk level beside it.
 * Nothing is computed — the ring only draws the stored score on the 0–100
 * scale it is already reported on.
 *
 * Risk colour lives here — on the finding surface — and never on the patient
 * identity surface, which stays constant for every patient.
 */
const riskTone: Record<RiskLevel, { surface: string; ink: string }> = {
  high: { surface: "var(--severe-bg)", ink: "var(--severe-fg)" },
  moderate: { surface: "var(--moderate-bg)", ink: "var(--moderate-fg)" },
  low: { surface: "var(--mild-bg)", ink: "var(--mild-fg)" },
};

const RING_RADIUS = 42;
const RING_LENGTH = 2 * Math.PI * RING_RADIUS;

export function SafetyScoreCard({
  safetyScore,
  riskLevel,
}: {
  safetyScore: number | null;
  riskLevel: RiskLevel | null;
}) {
  const risk = riskLevel ?? null;
  const tone = risk ? riskTone[risk] : { surface: "var(--surface-2)", ink: "var(--ink-3)" };
  // Bounded only so an out-of-range value cannot draw past the ring.
  const filled = safetyScore === null ? 0 : (Math.min(Math.max(safetyScore, 0), 100) / 100) * RING_LENGTH;

  return (
    <section aria-label="Safety score" className="pv-safety-score">
      <div className="pv-safety-ring">
        <svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">
          <circle className="pv-safety-ring-track" cx="50" cy="50" r={RING_RADIUS} />
          {safetyScore === null ? null : (
            <circle
              className="pv-safety-ring-value"
              cx="50"
              cy="50"
              r={RING_RADIUS}
              stroke={tone.ink}
              strokeDasharray={`${filled} ${RING_LENGTH}`}
              transform="rotate(-90 50 50)"
            />
          )}
        </svg>
        <span className="pv-safety-ring-number" style={safetyScore === null ? { color: "var(--ink-3)" } : undefined}>
          <span className={`pv-safety-ring-digits ${safetyScore === null ? "pv-safety-ring-digits-empty" : ""}`}>
            {safetyScore === null ? "—" : safetyScore}
          </span>
        </span>
      </div>

      <div className="pv-safety-score-copy">
        {risk ? (
          <p className="pv-safety-risk" style={{ color: tone.ink }}>
            {risk} risk
          </p>
        ) : (
          <p className="pv-safety-risk">Safety score</p>
        )}
        <p className="pv-safety-score-line">
          {risk ? "Safety score · " : ""}
          {safetyScore === null ? "Not recorded" : `${safetyScore} of 100`}
        </p>
        <p className="pv-safety-score-note">Set by the safety rules, not by AI.</p>
      </div>
    </section>
  );
}
