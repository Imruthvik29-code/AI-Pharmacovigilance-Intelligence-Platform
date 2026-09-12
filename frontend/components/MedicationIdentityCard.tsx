import { CapsuleIcon } from "@/components/icons/Icons";
import { IconChip } from "@/components/ui/IconChip";
import type { ReferenceDrugSearchResult } from "@/lib/api/types";
import { isBrandLikeTerm, termTypeLabel } from "@/lib/drugs/termType";

export function MedicationIdentityCard({ drug }: { drug: ReferenceDrugSearchResult }) {
  const brandLike = isBrandLikeTerm(drug.term_type);

  return (
    <div className="rounded-card bg-surface p-4 shadow-[var(--e-row)]">
      <div className="flex items-start gap-3">
        <IconChip Icon={CapsuleIcon} surface="var(--medications-bg)" ink="var(--medications-fg)" size="md" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{drug.name}</h3>
            <span className="rounded-full bg-surface-2 px-2.5 py-1 text-[0.6875rem] font-semibold uppercase tracking-wide text-ink-2">
              {termTypeLabel(drug.term_type)}
            </span>
          </div>
          <p className="mt-1.5 text-sm leading-5 text-ink-2">
            {brandLike
              ? "This is a branded medication. Its standardized identity can be used by the safety engine."
              : "This catalog identity can be used by the safety engine."}
          </p>
        </div>
      </div>
    </div>
  );
}
