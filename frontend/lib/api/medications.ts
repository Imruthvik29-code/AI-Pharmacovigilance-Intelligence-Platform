import { apiFetch } from "@/lib/api/client";
import type { MedicationCreate, MedicationResponse } from "@/lib/api/types";

export async function listMedications(patientId: string): Promise<MedicationResponse[]> {
  return apiFetch<MedicationResponse[]>(`/patients/${patientId}/medications`, {
    method: "GET",
  });
}

export async function createMedication(
  patientId: string,
  payload: MedicationCreate,
): Promise<MedicationResponse> {
  return apiFetch<MedicationResponse>(`/patients/${patientId}/medications`, {
    method: "POST",
    body: payload,
  });
}
