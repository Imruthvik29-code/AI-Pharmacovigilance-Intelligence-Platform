import type { ReferenceDrugSearchResult } from "@/lib/api/types";

const CACHE_KEY = "pv.drugNameCache";

export type CachedDrugName = {
  name: string;
  term_type: string | null;
  rxcui: string | null;
  source: string | null;
};

function readCache(): Record<string, CachedDrugName> {
  if (typeof window === "undefined") return {};
  const raw = window.localStorage.getItem(CACHE_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as Record<string, CachedDrugName>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeCache(cache: Record<string, CachedDrugName>): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
}

export function rememberDrug(drug: ReferenceDrugSearchResult): void {
  const cache = readCache();
  cache[drug.id] = {
    name: drug.name,
    term_type: drug.term_type,
    rxcui: drug.rxcui,
    source: drug.source,
  };
  writeCache(cache);
}

export function lookupDrug(drugId: string): CachedDrugName | null {
  return readCache()[drugId] ?? null;
}

export const UNCACHED_DRUG_LABEL = "Name not cached in this browser";

/** Human-readable label. Never returns a raw UUID. */
export function displayDrugName(drugId: string): {
  name: string;
  cached: boolean;
  termType: string | null;
} {
  const cached = lookupDrug(drugId);
  if (cached?.name) {
    return { name: cached.name, cached: true, termType: cached.term_type };
  }
  return { name: UNCACHED_DRUG_LABEL, cached: false, termType: null };
}
