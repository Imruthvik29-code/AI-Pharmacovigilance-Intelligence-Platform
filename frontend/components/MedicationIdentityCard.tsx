import type { ReferenceDrugSearchResult } from "@/lib/api/types";
import { isBrandLikeTerm, termTypeLabel } from "@/lib/drugs/termType";

export function MedicationIdentityCard({ drug }: { drug: ReferenceDrugSearchResult }) {
  const brandLike = isBrandLikeTerm(drug.term_type);

  return (
    <div className="rounded-2xl border border-line bg-paper p-4">
      <div className="flex items-start gap-3">
        <div aria-hidden="true" className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-card text-lg shadow-sm">💊</div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{drug.name}</h3>
            <span className="rounded-full bg-card px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted">
              {termTypeLabel(drug.term_type)}
            </span>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted">
            {brandLike
              ? "This is a branded medication. Its standardized identity can be used by the safety engine."
              : "This catalog identity can be used by the safety engine."}
          </p>
        </div>
      </div>
    </div>
  );
}
