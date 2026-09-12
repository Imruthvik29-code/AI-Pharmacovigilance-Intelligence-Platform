/**
 * Request/response types mirrored from backend/app/schemas/*.
 * Field names match the FastAPI JSON contract exactly.
 */

export type AuthUser = { id: string; email: string | null };
export type AuthResponse = { access_token: string; refresh_token: string | null; token_type: string; expires_in: number | null; user: AuthUser };
export type SignupRequest = { email: string; password: string };
export type LoginRequest = { email: string; password: string };
export type PatientRelation = "Self" | "Parent" | "Spouse" | "Child" | "Sibling" | "Grandparent" | "Other" | "Caregiver / dependent";
export type PatientResponse = { id: string; user_id: string; name: string; relation?: PatientRelation | null; age: number | null; sex: string | null; weight_kg: number | null; renal_flag: boolean; hepatic_flag: boolean; created_at: string; updated_at: string };
export type PatientCreate = { name: string; relation?: PatientRelation | null; age?: number | null; sex?: string | null; weight_kg?: number | null; renal_flag?: boolean; hepatic_flag?: boolean };
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
};
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
