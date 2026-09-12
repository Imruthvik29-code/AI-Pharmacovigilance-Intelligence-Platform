import type { ComponentType } from "react";
import {
  AlertIcon,
  CalendarIcon,
  CapsuleIcon,
  CheckIcon,
  ClockIcon,
  PulseIcon,
  ShieldIcon,
} from "@/components/icons/Icons";
import type { CategoryId } from "@/components/patient/categories";
import {
  activeMedicationCount,
  findingBreakdown,
  formatCalendarDate,
  formatShortDateTime,
  latestSymptom,
  latestTimelineEvent,
  peakSeverity,
  recentMedicationNames,
  severitySummary,
  unresolvedSymptomCount,
} from "@/lib/patient/summaries";
import type {
  AnalysisRunResponse,
  MedicationResponse,
  SymptomResponse,
  TimelineEventResponse,
} from "@/lib/api/types";

export type BriefRow = {
  key: string;
  Icon: ComponentType<{ className?: string }>;
  text: string;
  /** Optional secondary line, e.g. the recorded severity split. */
  sub?: string;
  surface: string;
  ink: string;
};

export type WorkspaceData = {
  analysis: AnalysisRunResponse | null;
  medications: MedicationResponse[];
  symptoms: SymptomResponse[];
  timeline: TimelineEventResponse[];
};

const NEUTRAL = { surface: "var(--surface-sunk)", ink: "var(--ink-2)" };
const SEVERITY_TONE = {
  severe: { surface: "var(--severe-surface)", ink: "var(--severe-ink)" },
  moderate: { surface: "var(--moderate-surface)", ink: "var(--moderate-ink)" },
  mild: { surface: "var(--mild-surface)", ink: "var(--mild-ink)" },
} as const;

/**
 * Compact metadata rows for the overview card — the reference's three-line
 * card body. Every value is read from the API payload; nothing is computed,
 * estimated or carried over between renders.
 */
export function briefRows(id: CategoryId, data: WorkspaceData): BriefRow[] {
  if (id === "safety") return safetyRows(data.analysis);
  if (id === "medications") return medicationRows(data.medications);
  if (id === "symptoms") return symptomRows(data.symptoms);
  return timelineRows(data.timeline);
}

/** One-line summary used by the desktop ribbon stack. */
export function briefSummary(id: CategoryId, data: WorkspaceData): string {
  if (id === "safety") {
    if (!data.analysis) return "Not analysed yet";
    const breakdown = findingBreakdown(data.analysis);
    if (!breakdown) return "Analysis recorded";
    return breakdown.total === 0
      ? "No findings recorded"
      : `${breakdown.total} ${breakdown.total === 1 ? "finding" : "findings"}`;
  }
  if (id === "medications") {
    return `${activeMedicationCount(data.medications)} active of ${data.medications.length}`;
  }
  if (id === "symptoms") {
    return `${unresolvedSymptomCount(data.symptoms)} unresolved of ${data.symptoms.length}`;
  }
  return `${data.timeline.length} ${data.timeline.length === 1 ? "event" : "events"}`;
}

function safetyRows(analysis: AnalysisRunResponse | null): BriefRow[] {
  if (!analysis) {
    return [
      {
        key: "not-run",
        Icon: ShieldIcon,
        text: "No analysis has been run for this record yet",
        ...NEUTRAL,
      },
    ];
  }

  // Three compact rows, matching the reference card body.
  const rows: BriefRow[] = [];
  const breakdown = findingBreakdown(analysis);
  const severity = peakSeverity(analysis);

  if (breakdown) {
    const tone = severity ? SEVERITY_TONE[severity] : SEVERITY_TONE.mild;
    rows.push({
      key: "findings",
      Icon: breakdown.total > 0 ? AlertIcon : CheckIcon,
      text:
        breakdown.total === 0
          ? "No interaction or ADR findings"
          : `${breakdown.total} safety ${breakdown.total === 1 ? "finding" : "findings"}`,
      sub: severitySummary(breakdown) || undefined,
      surface: breakdown.total > 0 ? tone.surface : SEVERITY_TONE.mild.surface,
      ink: breakdown.total > 0 ? tone.ink : SEVERITY_TONE.mild.ink,
    });
  }

  if (analysis.safety_score !== null && analysis.risk_level) {
    rows.push({
      key: "score",
      Icon: ShieldIcon,
      text: `Safety score ${analysis.safety_score} of 100 · ${analysis.risk_level} risk`,
      ...NEUTRAL,
    });
  }

  rows.push({
    key: "last-run",
    Icon: ClockIcon,
    text: `Last analysis ${formatShortDateTime(analysis.created_at)}`,
    ...NEUTRAL,
  });

  return rows;
}

function medicationRows(medications: MedicationResponse[]): BriefRow[] {
  const active = activeMedicationCount(medications);
  const rows: BriefRow[] = [
    {
      key: "active",
      Icon: CapsuleIcon,
      text:
        medications.length === 0
          ? "No medications recorded"
          : `${active} active of ${medications.length} recorded`,
      surface: "var(--medications-surface)",
      ink: "var(--medications-ink)",
    },
  ];

  const names = recentMedicationNames(medications);
  if (names.length > 0) {
    rows.push({ key: "names", Icon: CheckIcon, text: names.join(" · "), ...NEUTRAL });
  }
  return rows;
}

function symptomRows(symptoms: SymptomResponse[]): BriefRow[] {
  const unresolved = unresolvedSymptomCount(symptoms);
  const rows: BriefRow[] = [
    {
      key: "unresolved",
      Icon: PulseIcon,
      text:
        symptoms.length === 0
          ? "No symptoms reported"
          : `${unresolved} unresolved of ${symptoms.length} reported`,
      surface: "var(--symptoms-surface)",
      ink: "var(--symptoms-ink)",
    },
  ];

  const latest = latestSymptom(symptoms);
  if (latest) {
    rows.push({
      key: "latest",
      Icon: ClockIcon,
      text: latest.description,
      sub: `Onset ${formatCalendarDate(latest.onset_date)}`,
      ...NEUTRAL,
    });
  }
  return rows;
}

function timelineRows(timeline: TimelineEventResponse[]): BriefRow[] {
  const rows: BriefRow[] = [
    {
      key: "count",
      Icon: CalendarIcon,
      text:
        timeline.length === 0
          ? "No events recorded yet"
          : `${timeline.length} recorded ${timeline.length === 1 ? "event" : "events"}`,
      surface: "var(--timeline-surface)",
      ink: "var(--timeline-ink)",
    },
  ];

  const latest = latestTimelineEvent(timeline);
  if (latest) {
    rows.push({
      key: "latest",
      Icon: ClockIcon,
      text: latest.event_title,
      sub: formatShortDateTime(latest.event_time),
      ...NEUTRAL,
    });
  }
  return rows;
}
