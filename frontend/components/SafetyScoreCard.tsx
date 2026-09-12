import { ShieldIcon } from "@/components/icons/Icons";
import { IconChip } from "@/components/ui/IconChip";
import type { RiskLevel } from "@/lib/api/types";

/**
 * The deterministic score, presented as one of the detail screen's rows.
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
    <section aria-label="Safety score">
      <div className="pv-row">
        <IconChip Icon={ShieldIcon} surface={tone.surface} ink={tone.ink} size="md" />
        <div className="min-w-0 flex-1">
          <p className="pv-row-title">Safety score</p>
          <p className="pv-row-meta">
            {safetyScore === null ? "Not recorded" : `${safetyScore} of 100`}
            {risk ? " · " : ""}
            {risk ? <span style={{ color: tone.ink }}>{risk} risk</span> : null}
          </p>
        </div>
        <p
          className="flex-none text-[1.75rem] font-bold leading-none tracking-[-0.03em]"
          style={{ color: safetyScore === null ? "var(--ink-3)" : tone.ink }}
        >
          {safetyScore === null ? "—" : safetyScore}
        </p>
      </div>
      <p className="mt-2 px-1 text-[0.75rem] leading-5 text-ink-3">
        Out of 100. Produced by rule engines, not by the language model.
      </p>
    </section>
  );
}
