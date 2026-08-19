import type {
  AdherenceFinding,
  AdrFinding,
  AnalysisRunResponse,
  DeterministicResult,
  InteractionFinding,
  PenaltyEntry,
} from "@/lib/api/types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asArray<T>(value: unknown, map: (item: Record<string, unknown>) => T | null): T[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (isRecord(item) ? map(item) : null))
    .filter((item): item is T => item !== null);
}

export function parseDeterministicResult(
  value: AnalysisRunResponse["deterministic_result"],
): DeterministicResult | null {
  if (!isRecord(value)) return null;

  const interaction_findings = asArray<InteractionFinding>(value.interaction_findings, (item) => ({
    interaction_rule_id: String(item.interaction_rule_id ?? ""),
    drug_a_id: String(item.drug_a_id ?? ""),
    drug_a_name: String(item.drug_a_name ?? "Unknown drug"),
    drug_b_id: String(item.drug_b_id ?? ""),
    drug_b_name: String(item.drug_b_name ?? "Unknown drug"),
    severity: (item.severity as InteractionFinding["severity"]) ?? "mild",
    mechanism: item.mechanism == null ? null : String(item.mechanism),
    recommendation: item.recommendation == null ? null : String(item.recommendation),
    source: item.source == null ? null : String(item.source),
  }));

  const adr_findings = asArray<AdrFinding>(value.adr_findings, (item) => ({
    adr_rule_id: String(item.adr_rule_id ?? ""),
    drug_id: String(item.drug_id ?? ""),
    drug_name: String(item.drug_name ?? "Unknown drug"),
    reaction_description: String(item.reaction_description ?? ""),
    severity: (item.severity as AdrFinding["severity"]) ?? "mild",
    frequency_class: item.frequency_class == null ? null : String(item.frequency_class),
    source: item.source == null ? null : String(item.source),
  }));

  const adherence_findings = asArray<AdherenceFinding>(value.adherence_findings, (item) => ({
    medication_id: String(item.medication_id ?? ""),
    drug_name: String(item.drug_name ?? "Unknown drug"),
    taken: Number(item.taken ?? 0),
    missed: Number(item.missed ?? 0),
    skipped: Number(item.skipped ?? 0),
    due: Number(item.due ?? 0),
    adherence_rate: item.adherence_rate == null ? null : Number(item.adherence_rate),
  }));

  const penalties = asArray<PenaltyEntry>(value.penalties, (item) => ({
    category: String(item.category ?? ""),
    description: String(item.description ?? ""),
    severity: (item.severity as PenaltyEntry["severity"]) ?? "mild",
    points: Number(item.points ?? 0),
  }));

  return {
    safety_score: Number(value.safety_score ?? 0),
    risk_level: (value.risk_level as DeterministicResult["risk_level"]) ?? "low",
    starting_score: Number(value.starting_score ?? 0),
    total_points_deducted: Number(value.total_points_deducted ?? 0),
    interaction_findings,
    adr_findings,
    adherence_findings,
    penalties,
  };
}

export const EDUCATIONAL_DISCLAIMER =
  "This project is an educational and research-oriented pharmacovigilance application. It is not intended to replace professional medical advice, diagnosis, or treatment. The AI explains deterministic medication safety findings and should not be relied upon as the sole basis for clinical decisions.";
