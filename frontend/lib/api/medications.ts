import { apiFetch } from "@/lib/api/client";
import type { MedicationCreate, MedicationResponse, MedicationUpdate } from "@/lib/api/types";

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

/**
 * Partial update. Only keys present in `payload` are changed, so a caller
 * that sends only `dose_rules` leaves every other field of the course as it
 * was. Never triggers schedule generation.
 */
export async function updateMedication(
  medicationId: string,
  payload: MedicationUpdate,
): Promise<MedicationResponse> {
  return apiFetch<MedicationResponse>(`/medications/${medicationId}`, {
    method: "PUT",
    body: payload,
  });
}
