import type { ReferenceDrugSearchResult } from "@/lib/api/types";

const TTY_LABELS: Record<string, string> = {
  SBD: "Branded medication",
  SBDF: "Branded dose form",
  BPCK: "Branded pack",
  SCD: "Clinical medication",
  SCDF: "Clinical dose form",
  GPCK: "Generic pack",
  IN: "Active ingredient",
  PIN: "Precise ingredient",
  MIN: "Multiple ingredients",
  DF: "Dose form",
};

export function termTypeLabel(termType: string | null): string {
  return (termType && TTY_LABELS[termType]) || "Medication catalog match";
}

export function isBrandLikeTerm(termType: string | null): boolean {
  return termType === "SBD" || termType === "BPCK" || termType === "BN";
}

export function isIngredientTerm(termType: string | null): boolean {
  return termType === "IN" || termType === "PIN" || termType === "MIN";
}

export function medicationSearchSubtitle(drug: ReferenceDrugSearchResult): string {
  if (drug.term_type) return termTypeLabel(drug.term_type);
  if (drug.source) return drug.source;
  return "Medication catalog match";
}
