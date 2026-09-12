import { apiFetch } from "@/lib/api/client";
import type { SymptomCreate, SymptomResponse } from "@/lib/api/types";

export async function listSymptoms(patientId: string): Promise<SymptomResponse[]> {
  return apiFetch<SymptomResponse[]>(`/patients/${patientId}/symptoms`, {
    method: "GET",
  });
}

export async function createSymptom(
  patientId: string,
  payload: SymptomCreate,
): Promise<SymptomResponse> {
  return apiFetch<SymptomResponse>(`/patients/${patientId}/symptoms`, {
    method: "POST",
    body: payload,
  });
}
