import { apiFetch } from "@/lib/api/client";
import type { PatientCreate, PatientResponse } from "@/lib/api/types";

export async function listPatients(): Promise<PatientResponse[]> {
  return apiFetch<PatientResponse[]>("/patients", { method: "GET" });
}

export async function createPatient(payload: PatientCreate): Promise<PatientResponse> {
  return apiFetch<PatientResponse>("/patients", {
    method: "POST",
    body: payload,
  });
}

export async function getPatient(patientId: string): Promise<PatientResponse> {
  return apiFetch<PatientResponse>(`/patients/${patientId}`, { method: "GET" });
}
