"use client";

import { displayDrugName } from "@/lib/drugs/nameCache";
import type { MedicationResponse } from "@/lib/api/types";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";

export function MedicationList({
  medications,
  loading,
  error,
}: {
  medications: MedicationResponse[];
  loading?: boolean;
  error?: string | null;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-line bg-card shadow-[0_1px_2px_rgba(20,32,41,0.04)]" aria-label="Medications">
      <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">Treatment</p>
          <h2 className="mt-1 text-base font-semibold tracking-tight">Medications</h2>
          <p className="mt-1 text-xs text-muted">Current medication record.</p>
        </div>
        <span className="rounded-full bg-paper px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-muted">
          {medications.length} {medications.length === 1 ? "item" : "items"}
        </span>
      </div>
      <div className="px-5 pb-5">
        {loading ? (
          <div className="pt-4">
            <LoadingSkeleton label="Loading medications" lines={3} />
          </div>
        ) : null}
        {error ? (
          <p className="pt-4 text-sm text-high" role="alert">
            {error}
          </p>
        ) : null}
        {!loading && !error && medications.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-line bg-paper/60 px-4 py-5">
            <p className="text-sm font-medium">No medications recorded</p>
            <p className="mt-1 text-sm leading-6 text-muted">
              Search the catalog to add an active course to this patient.
            </p>
          </div>
        ) : null}
        {!loading && medications.length > 0 ? (
          <ul className="mt-2 divide-y divide-line">
            {medications.map((medication) => {
              const cached = displayDrugName(medication.drug_id);
              const name = medication.drug_name ?? cached.name;
              const termType = medication.drug_term_type ?? cached.termType;
              const genericContext = medication.drug_generic_name && medication.drug_generic_name !== name
                ? medication.drug_generic_name
                : null;
              const identityVerified = Boolean(medication.drug_name);
              return (
                <li key={medication.id} className="py-4 first:pt-3 last:pb-0">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className={`truncate font-medium ${identityVerified || cached.cached ? "text-ink" : "text-muted"}`}>
                          {name}
                        </p>
                        {identityVerified ? (
                          <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent">
                            Verified
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-xs text-muted">
                        {[termType, genericContext, medication.dose]
                          .filter(Boolean)
                          .join(" · ") || "Medication details not recorded"}
                      </p>
                    </div>
                    <span className="shrink-0 rounded-full border border-line px-2 py-1 font-mono text-[10px] uppercase tracking-wide text-muted">
                      {medication.status}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                    {medication.start_date ? <span>Started {medication.start_date}</span> : null}
                    {medication.end_date ? <span>Ends {medication.end_date}</span> : null}
                    {medication.times_per_day != null ? <span>{medication.times_per_day}× daily</span> : null}
                  </div>
                  {medication.purpose_text ? (
                    <p className="mt-2 text-sm leading-5 text-muted">{medication.purpose_text}</p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
