"use client";

import { IconChip } from "@/components/ui/IconChip";
import { CapsuleIcon, CheckIcon } from "@/components/icons/Icons";
import { displayDrugName } from "@/lib/drugs/nameCache";
import { termTypeLabel } from "@/lib/drugs/termType";
import { formatCalendarDate } from "@/lib/patient/summaries";
import type { MedicationResponse } from "@/lib/api/types";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";

/** The recorded course details, in reading order. Absent values are left out. */
function prescriptionFacts(medication: MedicationResponse): Array<{ label: string; value: string }> {
  const facts: Array<{ label: string; value: string }> = [];
  if (medication.times_per_day != null) {
    facts.push({ label: "Frequency", value: `${medication.times_per_day}× daily` });
  }
  if (medication.interval_hours != null) {
    facts.push({ label: "Interval", value: `Every ${medication.interval_hours} h` });
  }
  if (medication.duration_days != null) {
    facts.push({
      label: "Duration",
      value: `${medication.duration_days} ${medication.duration_days === 1 ? "day" : "days"}`,
    });
  }
  if (medication.start_date) {
    facts.push({ label: "Started", value: formatCalendarDate(medication.start_date) });
  }
  if (medication.end_date) {
    facts.push({ label: "Ends", value: formatCalendarDate(medication.end_date) });
  }
  return facts;
}

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

      <div className={`${showHeading ? "mt-3" : ""} pv-meds-list`}>
        {loading ? <LoadingSkeleton label="Loading medications" lines={3} /> : null}
        {error ? (
          <p className="pv-meds-alert" role="alert">
            {error}
          </p>
        ) : null}
        {!loading && !error && medications.length === 0 ? (
          <div className="pv-meds-card pv-meds-empty">
            <IconChip Icon={CapsuleIcon} surface="var(--surface-2)" ink="var(--ink-3)" size="md" />
            <div className="min-w-0">
              <p className="pv-meds-empty-title">No medications recorded</p>
              <p className="pv-meds-empty-text">
                Search the catalog to add an active course to this patient.
              </p>
            </div>
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
              const active = medication.status === "active";
              const facts = prescriptionFacts(medication);

              return (
                <article
                  key={medication.id}
                  className={`pv-meds-card pv-meds-item ${active ? "" : "is-inactive"}`}
                >
                  <div className="pv-meds-item-head">
                    <IconChip
                      Icon={CapsuleIcon}
                      surface={active ? "var(--medications-bg)" : "var(--surface-2)"}
                      ink={active ? "var(--medications-fg)" : "var(--ink-3)"}
                      size="md"
                    />
                    <div className="pv-meds-identity">
                      <h3
                        className={`pv-meds-name ${identityVerified || cached.cached ? "" : "is-unnamed"}`}
                      >
                        {name}
                      </h3>
                      <p className="pv-meds-kind">
                        {[termType, genericContext, medication.dose].filter(Boolean).join(" · ") ||
                          "Medication details not recorded"}
                      </p>
                      <div className="pv-meds-tags">
                        <span className={`pv-meds-status ${active ? "is-active" : ""}`}>
                          <span className="pv-meds-status-text">{medication.status.replace(/_/g, " ")}</span>
                        </span>
                        {identityVerified ? (
                          <span className="pv-meds-verified">
                            <CheckIcon className="pv-meds-verified-icon" />
                            <span>Verified</span>
                          </span>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  {facts.length > 0 || medication.purpose_text ? (
                    <dl className="pv-meds-facts">
                      {facts.map((fact) => (
                        <div key={fact.label} className="pv-meds-fact">
                          <dt>{fact.label}</dt>
                          <dd>{fact.value}</dd>
                        </div>
                      ))}
                      {medication.purpose_text ? (
                        <div className="pv-meds-fact pv-meds-fact-wide">
                          <dt>Purpose</dt>
                          <dd>{medication.purpose_text}</dd>
                        </div>
                      ) : null}
                    </dl>
                  ) : null}
                </article>
              );
            })
          : null}
      </div>
    </section>
  );
}
