import { apiFetch } from "@/lib/api/client";
import type { MedicationDoseResponse, MedicationDoseMarkRequest, UpcomingDoseResponse } from "@/lib/api/types";

export async function generateMedicationSchedule(medicationId: string): Promise<MedicationDoseResponse[]> {
  return apiFetch<MedicationDoseResponse[]>(`/medications/${medicationId}/schedule`, { method: "POST" });
}

export async function listUpcomingDoses(patientId: string): Promise<UpcomingDoseResponse[]> {
  return apiFetch<UpcomingDoseResponse[]>(`/patients/${patientId}/doses/upcoming`, { method: "GET" });
}

export async function markDose(doseId: string, payload: MedicationDoseMarkRequest): Promise<MedicationDoseResponse> {
  return apiFetch<MedicationDoseResponse>(`/doses/${doseId}/mark`, { method: "POST", body: payload });
}
