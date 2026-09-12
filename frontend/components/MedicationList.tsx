"use client";

import { IconChip } from "@/components/ui/IconChip";
import { CapsuleIcon } from "@/components/icons/Icons";
import { displayDrugName } from "@/lib/drugs/nameCache";
import { termTypeLabel } from "@/lib/drugs/termType";
import type { MedicationResponse } from "@/lib/api/types";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";

export function MedicationList({
  medications,
  loading,
  error,
  showHeading = true,
}: {
  medications: MedicationResponse[];
  loading?: boolean;
  error?: string | null;
  /** Off when the surrounding DetailSheet already names the section. */
  showHeading?: boolean;
}) {
  return (
    <section aria-label="Medications">
      {showHeading ? (
        <div className="flex items-end justify-between gap-4 px-1">
          <div>
            <p className="pv-eyebrow">
              Treatment
            </p>
            <h2 className="pv-section-title mt-0.5">Medications</h2>
          </div>
          <span className="text-[0.75rem] text-ink-3">
            {medications.length} {medications.length === 1 ? "item" : "items"}
          </span>
        </div>
      ) : null}

      <div className={`${showHeading ? "mt-3" : ""} space-y-2`}>
        {loading ? <LoadingSkeleton label="Loading medications" lines={3} /> : null}
        {error ? (
          <p className="rounded-row bg-severe-bg px-4 py-3 text-[0.875rem] text-severe" role="alert">
            {error}
          </p>
        ) : null}
        {!loading && !error && medications.length === 0 ? (
          <div className="rounded-row bg-surface-2 px-4 py-5">
            <p className="text-[0.9375rem] font-semibold">No medications recorded</p>
            <p className="mt-1 text-[0.875rem] leading-6 text-ink-2">
              Search the catalog to add an active course to this patient.
            </p>
          </div>
        ) : null}

        {!loading && medications.length > 0
          ? medications.map((medication) => {
              const cached = displayDrugName(medication.drug_id);
              const name = medication.drug_name ?? cached.name;
              const termType = medication.drug_term_type
                ? termTypeLabel(medication.drug_term_type)
                : cached.termType
                  ? termTypeLabel(cached.termType)
                  : null;
              const genericContext =
                medication.drug_generic_name && medication.drug_generic_name !== name
                  ? medication.drug_generic_name
                  : null;
              const identityVerified = Boolean(medication.drug_name);

              return (
                <article key={medication.id} className="pv-row items-start">
                  <IconChip
                    Icon={CapsuleIcon}
                    surface="var(--medications-surface)"
                    ink="var(--medications-ink)"
                    size="sm"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <p
                          className={`truncate font-semibold tracking-[-0.01em] ${identityVerified || cached.cached ? "text-ink" : "text-ink-3"}`}
                        >
                          {name}
                        </p>
                        {identityVerified ? (
                          <span className="rounded-full bg-medications px-2 py-0.5 text-[0.6875rem] font-semibold text-medications-ink">
                            Verified
                          </span>
                        ) : null}
                      </div>
                      <span className="shrink-0 rounded-full bg-surface-2 px-2.5 py-0.5 text-[0.6875rem] font-semibold capitalize text-ink-2">
                        {medication.status}
                      </span>
                    </div>
                    <p className="mt-1 text-[0.8125rem] text-ink-2">
                      {[termType, genericContext, medication.dose].filter(Boolean).join(" · ") ||
                        "Medication details not recorded"}
                    </p>
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[0.75rem] text-ink-3">
                      {medication.start_date ? <span>Started {medication.start_date}</span> : null}
                      {medication.end_date ? <span>Ends {medication.end_date}</span> : null}
                      {medication.times_per_day != null ? (
                        <span>{medication.times_per_day}× daily</span>
                      ) : null}
                    </div>
                    {medication.purpose_text ? (
                      <p className="mt-1.5 text-[0.8125rem] leading-5 text-ink-2">
                        {medication.purpose_text}
                      </p>
                    ) : null}
                  </div>
                </article>
              );
            })
          : null}
      </div>
    </section>
  );
}
