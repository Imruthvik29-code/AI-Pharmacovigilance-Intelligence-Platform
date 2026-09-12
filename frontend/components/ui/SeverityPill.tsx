import type { SeverityLevel } from "@/lib/api/types";

const TONES: Record<SeverityLevel, { surface: string; ink: string }> = {
  severe: { surface: "var(--severe-surface)", ink: "var(--severe-ink)" },
  moderate: { surface: "var(--moderate-surface)", ink: "var(--moderate-ink)" },
  mild: { surface: "var(--mild-surface)", ink: "var(--mild-ink)" },
};

/**
 * One severity badge for the whole app. Replaces the three divergent
 * implementations that previously lived in AnalysisReport, SymptomPanel and
 * MedicationList. Renders nothing when there is no severity to report.
 */
export function SeverityPill({ severity }: { severity: SeverityLevel | null | undefined }) {
  if (!severity) return null;
  const tone = TONES[severity];
  return (
    <span
      className="inline-flex flex-none items-center rounded-full px-2.5 py-1 text-[0.6875rem] font-semibold capitalize"
      style={{ backgroundColor: tone.surface, color: tone.ink }}
    >
      {severity}
    </span>
  );
}

export function severityTone(severity: SeverityLevel) {
  return TONES[severity];
}
