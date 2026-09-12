import { parseDeterministicResult } from "@/lib/analysis/deterministic";
import type {
  AnalysisRunResponse,
  MedicationResponse,
  SeverityLevel,
  SymptomResponse,
  TimelineEventResponse,
} from "@/lib/api/types";

/**
 * Pure read-only derivations over data the API already returns.
 * Nothing here computes a clinical value: counting and grouping only. The
 * safety score and risk level are read straight from the analysis run.
 */

export type FindingBreakdown = {
  total: number;
  interactions: number;
  adrs: number;
  bySeverity: Record<SeverityLevel, number>;
};

/** Counts interaction + ADR findings and groups them by their recorded severity. */
export function findingBreakdown(run: AnalysisRunResponse | null): FindingBreakdown | null {
  if (!run) return null;
  const result = parseDeterministicResult(run.deterministic_result);
  if (!result) return null;

  const bySeverity: Record<SeverityLevel, number> = { severe: 0, moderate: 0, mild: 0 };
  for (const finding of result.interaction_findings) bySeverity[finding.severity] += 1;
  for (const finding of result.adr_findings) bySeverity[finding.severity] += 1;

  return {
    total: result.interaction_findings.length + result.adr_findings.length,
    interactions: result.interaction_findings.length,
    adrs: result.adr_findings.length,
    bySeverity,
  };
}

/** Highest severity present across interaction + ADR findings, or null. */
export function peakSeverity(run: AnalysisRunResponse | null): SeverityLevel | null {
  const breakdown = findingBreakdown(run);
  if (!breakdown || breakdown.total === 0) return null;
  if (breakdown.bySeverity.severe > 0) return "severe";
  if (breakdown.bySeverity.moderate > 0) return "moderate";
  return "mild";
}

/** Human-readable severity split, e.g. "1 severe · 2 moderate". Empty when none. */
export function severitySummary(breakdown: FindingBreakdown | null): string {
  if (!breakdown || breakdown.total === 0) return "";
  const order: SeverityLevel[] = ["severe", "moderate", "mild"];
  return order
    .filter((severity) => breakdown.bySeverity[severity] > 0)
    .map((severity) => `${breakdown.bySeverity[severity]} ${severity}`)
    .join(" · ");
}

/** Distinct `source` values actually present on the findings. Never substituted. */
export function evidenceSources(run: AnalysisRunResponse | null): string[] {
  if (!run) return [];
  const result = parseDeterministicResult(run.deterministic_result);
  if (!result) return [];
  const sources = [
    ...result.interaction_findings.map((finding) => finding.source),
    ...result.adr_findings.map((finding) => finding.source),
  ].filter((source): source is string => Boolean(source && source.trim()));
  return [...new Set(sources)];
}

export function activeMedicationCount(medications: MedicationResponse[]): number {
  return medications.filter((medication) => medication.status === "active").length;
}

export function unresolvedSymptomCount(symptoms: SymptomResponse[]): number {
  return symptoms.filter((symptom) => !symptom.resolved_date).length;
}

export function latestSymptom(symptoms: SymptomResponse[]): SymptomResponse | null {
  if (symptoms.length === 0) return null;
  return [...symptoms].sort((a, b) => b.onset_date.localeCompare(a.onset_date))[0];
}

export function latestTimelineEvent(events: TimelineEventResponse[]): TimelineEventResponse | null {
  if (events.length === 0) return null;
  return [...events].sort((a, b) => b.event_time.localeCompare(a.event_time))[0];
}

/** Two most recently started medications, for the compact overview metadata. */
export function recentMedicationNames(medications: MedicationResponse[], limit = 2): string[] {
  return [...medications]
    .sort((a, b) => (b.start_date ?? "").localeCompare(a.start_date ?? ""))
    .map((medication) => medication.drug_name)
    .filter((name): name is string => Boolean(name))
    .slice(0, limit);
}

/** Locale date+time for display, with an ISO string available for `title`. */
export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Compact form for the overview card, where width is tight. */
export function formatShortDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatCalendarDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Demographic line for the hero. Never invents a value that is absent. */
export function demographicLine(patient: {
  age: number | null;
  sex: string | null;
  relation?: string | null;
}): string {
  const parts = [
    patient.age != null ? `${patient.age} yrs` : null,
    patient.sex,
    patient.relation ? (patient.relation === "Self" ? "My profile" : patient.relation) : null,
  ].filter(Boolean);
  return parts.join(" · ") || "No demographics recorded";
}
