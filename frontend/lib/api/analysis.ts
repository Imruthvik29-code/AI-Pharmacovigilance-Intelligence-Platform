import { apiFetch } from "@/lib/api/client";
import type { AnalysisRunResponse } from "@/lib/api/types";

/** POST /patients/{id}/analyze — empty body; analysis is derived server-side. */
export async function runAnalysis(patientId: string): Promise<AnalysisRunResponse> {
  return apiFetch<AnalysisRunResponse>(`/patients/${patientId}/analyze`, {
    method: "POST",
  });
}

export async function listAnalysisRuns(patientId: string): Promise<AnalysisRunResponse[]> {
  return apiFetch<AnalysisRunResponse[]>(`/patients/${patientId}/analysis`, {
    method: "GET",
  });
}
