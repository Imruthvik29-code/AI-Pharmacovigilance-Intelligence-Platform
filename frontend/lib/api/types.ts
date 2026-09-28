/**
 * Request/response types mirrored from backend/app/schemas/*.
 * Field names match the FastAPI JSON contract exactly.
 */

export type AuthUser = { id: string; email: string | null };
export type AuthResponse = { access_token: string; refresh_token: string | null; token_type: string; expires_in: number | null; user: AuthUser };
export type SignupRequest = { email: string; password: string };
export type LoginRequest = { email: string; password: string };
export type PatientRelation = "Self" | "Parent" | "Spouse" | "Child" | "Sibling" | "Grandparent" | "Other" | "Caregiver / dependent";
/**
 * Daily routine context recorded against the patient, not the prescription.
 * `timezone` is an IANA key; meal values are local wall-clock "HH:MM[:SS]"
 * strings, never instants. All optional -- absent means not recorded.
 */
export type PatientRoutine = {
  timezone?: string | null;
  breakfast_time?: string | null;
  lunch_time?: string | null;
  dinner_time?: string | null;
};
export type PatientResponse = { id: string; user_id: string; name: string; relation?: PatientRelation | null; age: number | null; sex: string | null; weight_kg: number | null; renal_flag: boolean; hepatic_flag: boolean; timezone: string | null; breakfast_time: string | null; lunch_time: string | null; dinner_time: string | null; created_at: string; updated_at: string };
export type PatientCreate = { name: string; relation?: PatientRelation | null; age?: number | null; sex?: string | null; weight_kg?: number | null; renal_flag?: boolean; hepatic_flag?: boolean } & PatientRoutine;
/** Partial update -- only the keys sent are changed (backend uses exclude_unset). */
export type PatientUpdate = { name?: string; relation?: PatientRelation | null; age?: number | null; sex?: string | null; weight_kg?: number | null; renal_flag?: boolean; hepatic_flag?: boolean } & PatientRoutine;
export type MedicationStatus = "active" | "completed" | "completed_early" | "paused" | "discontinued";
export type MedicationResponse = {
  id: string;
  patient_id: string;
  condition_id: string | null;
  purpose_text: string | null;
  drug_id: string;
  dose: string | null;
  times_per_day: number | null;
  interval_hours: number | null;
  duration_days: number | null;
  status: MedicationStatus;
  start_date: string;
  end_date: string | null;
  created_at: string;
  updated_at: string;
  drug_name: string | null;
  drug_generic_name: string | null;
  drug_term_type: string | null;
  drug_source: string | null;
  /**
   * Optional on purpose. `undefined` means the rules were not part of the
   * response, which is not the same as `[]` (loaded, and there are none).
   * Treating the two alike would let a save that nobody meant as a clear
   * wipe a prescription's timing.
   */
  dose_rules?: DoseRuleResponse[];
};
/** Mirrors backend/app/schemas/dose_rule.py. */
export type DoseAnchor = "breakfast" | "lunch" | "dinner" | "clock_time";
export type DoseRelation = "before" | "with" | "after";
export type DoseRuleInput = {
  sequence: number;
  anchor_type: DoseAnchor;
  anchor_relation?: DoseRelation | null;
  offset_minutes?: number | null;
  clock_time?: string | null;
  /** null inherits the medication-level dose. */
  dose?: string | null;
};
export type DoseRuleResponse = {
  id: string;
  medication_id: string;
  sequence: number;
  anchor_type: DoseAnchor;
  anchor_relation: DoseRelation | null;
  offset_minutes: number | null;
  clock_time: string | null;
  dose: string | null;
  created_at: string;
  updated_at: string;
};
/**
 * Partial update, backend `exclude_unset` semantics: omit `dose_rules` to
 * leave them unchanged, send `[]` to clear them, send a list to replace the
 * set. The backend rejects `null`, so the type does not allow it.
 */
export type MedicationUpdate = { dose_rules?: DoseRuleInput[] };
export type MedicationCreate = { drug_id: string; start_date: string; status?: MedicationStatus; purpose_text?: string | null; dose?: string | null; times_per_day?: number | null; interval_hours?: number | null; duration_days?: number | null; end_date?: string | null; condition_id?: string | null };
export type ReferenceDrugSearchResult = { id: string; name: string; generic_name: string | null; rxcui: string | null; source: string | null; term_type: string | null };
export type RiskLevel = "low" | "moderate" | "high";
export type ConfidenceLevel = "low" | "moderate" | "high";
export type SeverityLevel = "mild" | "moderate" | "severe";
export type InteractionFinding = { interaction_rule_id: string; drug_a_id: string; drug_a_name: string; drug_b_id: string; drug_b_name: string; severity: SeverityLevel; mechanism: string | null; recommendation: string | null; source: string | null };
export type AdrFinding = { adr_rule_id: string; drug_id: string; drug_name: string; reaction_description: string; severity: SeverityLevel; frequency_class: string | null; source: string | null };
export type AdherenceFinding = { medication_id: string; drug_name: string; taken: number; missed: number; skipped: number; due: number; adherence_rate: number | null };
export type PenaltyEntry = { category: string; description: string; severity: SeverityLevel; points: number };
export type DeterministicResult = { safety_score: number; risk_level: RiskLevel; starting_score: number; total_points_deducted: number; interaction_findings: InteractionFinding[]; adr_findings: AdrFinding[]; adherence_findings: AdherenceFinding[]; penalties: PenaltyEntry[] };
export type AnalysisRunResponse = { id: string; patient_id: string; analysis_version: string; deterministic_result: DeterministicResult | Record<string, unknown> | null; safety_score: number | null; risk_level: RiskLevel | null; llm_summary: string | null; llm_reasoning: string | null; llm_recommendations: string | null; confidence_score: number | null; confidence_level: ConfidenceLevel | null; created_at: string };
export type TimelineEventResponse = { id: string; patient_id: string; event_type: string; ref_id: string | null; event_title: string; event_description: string | null; event_time: string; payload: Record<string, unknown> | null; created_at: string };
export type DoseStatus = "taken" | "missed" | "skipped";
export type MedicationDoseResponse = { id: string; medication_id: string; schedule_id: string | null; scheduled_time: string; status: DoseStatus | null; actual_time: string | null; created_at: string; updated_at: string };
export type UpcomingDoseResponse = { id: string; medication_id: string; scheduled_time: string; drug_name: string; dose: string | null };
export type MedicationDoseMarkRequest = { status: DoseStatus; actual_time?: string | null };
export type SymptomSeverity = "mild" | "moderate" | "severe";
export type SymptomResponse = {
  id: string;
  patient_id: string;
  condition_id: string | null;
  medication_id: string | null;
  description: string;
  severity: SymptomSeverity;
  onset_date: string;
  resolved_date: string | null;
  created_at: string;
  updated_at: string;
};
export type SymptomCreate = {
  description: string;
  severity?: SymptomSeverity;
  condition_id?: string | null;
  medication_id?: string | null;
  onset_date?: string | null;
  resolved_date?: string | null;
};
export const REFERENCE_DRUG_MIN_QUERY_LENGTH = 2;
