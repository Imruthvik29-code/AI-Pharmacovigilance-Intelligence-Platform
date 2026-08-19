import { apiFetch } from "@/lib/api/client";
import {
  REFERENCE_DRUG_MIN_QUERY_LENGTH,
  type ReferenceDrugSearchResult,
} from "@/lib/api/types";

export async function searchReferenceDrugs(
  query: string,
  limit = 20,
): Promise<ReferenceDrugSearchResult[]> {
  const q = query.trim();
  if (q.length < REFERENCE_DRUG_MIN_QUERY_LENGTH) {
    return [];
  }
  const params = new URLSearchParams({
    q,
    limit: String(limit),
  });
  return apiFetch<ReferenceDrugSearchResult[]>(
    `/reference-drugs/search?${params.toString()}`,
    { method: "GET" },
  );
}
