import { apiFetch } from "@/lib/api/client";
import type { TimelineEventResponse } from "@/lib/api/types";

export async function listTimeline(patientId: string): Promise<TimelineEventResponse[]> {
  return apiFetch<TimelineEventResponse[]>(`/patients/${patientId}/timeline`, {
    method: "GET",
  });
}
