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
    <section className="rounded-2xl border border-line bg-card p-5" aria-label="Medications">
      <h2 className="text-sm font-semibold">Medications</h2>
      <p className="mt-1 text-xs text-muted">Current medication record.</p>
      {loading ? (
        <div className="mt-4">
          <LoadingSkeleton label="Loading medications" lines={3} />
        </div>
      ) : null}
      {error ? (
        <p className="mt-4 text-sm text-high" role="alert">
          {error}
        </p>
      ) : null}
      {!loading && !error && medications.length === 0 ? (
        <p className="mt-4 text-sm leading-6 text-muted">
          No medications yet. Search the catalog to add an active course.
        </p>
      ) : null}
      {!loading && medications.length > 0 ? (
        <ul className="mt-4 divide-y divide-line">
          {medications.map((medication) => {
            const displayed = displayDrugName(medication.drug_id);
            return (
              <li key={medication.id} className="py-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className={`font-medium ${displayed.cached ? "text-ink" : "text-muted"}`}>
                    {displayed.name}
                  </p>
                  <span className="font-mono text-[11px] uppercase tracking-wide text-muted">
                    {medication.status}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted">
                  {[
                    displayed.termType,
                    medication.dose,
                    medication.start_date ? `Started ${medication.start_date}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                {medication.purpose_text ? (
                  <p className="mt-1 text-sm text-muted">{medication.purpose_text}</p>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
