"use client";

import { useState } from "react";
import { IconChip } from "@/components/ui/IconChip";
import { CapsuleIcon, CheckIcon } from "@/components/icons/Icons";
import { displayDrugName } from "@/lib/drugs/nameCache";
import { termTypeLabel } from "@/lib/drugs/termType";
import { formatCalendarDate } from "@/lib/patient/summaries";
import type { MedicationResponse, PatientResponse } from "@/lib/api/types";
import { describeRule } from "@/lib/medications/doseRules";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { DoseRuleEditor } from "@/components/DoseRuleEditor";

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

/**
 * The course's daily dose timing: a read-only summary, and the editor on
 * request. Nothing here generates a schedule.
 */
function DoseTiming({
  medication,
  patient,
  onUpdated,
}: {
  medication: MedicationResponse;
  patient: PatientResponse | null;
  onUpdated: (updated: MedicationResponse) => void;
}) {
  const [editing, setEditing] = useState(false);
  const rules = medication.dose_rules;

  // Not part of the response: offering an editor here would risk a save
  // that clears timing the UI simply never loaded.
  if (rules === undefined) return null;

  // Interval courses are spaced by hours; dose timing does not apply.
  if (medication.interval_hours != null && rules.length === 0) {
    return (
      <section className="pv-timing" aria-label="Dose timing">
        <p className="pv-timing-title">Dose timing</p>
        <p className="pv-timing-empty">
          Scheduled every {medication.interval_hours} h, so dose timing isn&apos;t used.
        </p>
      </section>
    );
  }

  // Frequency never recorded: the schedule panel already says so.
  if (medication.times_per_day == null && rules.length === 0) return null;

  const ordered = [...rules].sort((a, b) => a.sequence - b.sequence);
  const name = medication.drug_name ?? "this medication";

  return (
    <section className="pv-timing" aria-label="Dose timing">
      <div className="pv-timing-head">
        <p className="pv-timing-title">Dose timing</p>
        {editing ? null : (
          <button type="button" onClick={() => setEditing(true)} aria-expanded={false}
            className="pv-meds-quiet-button" aria-label={`${ordered.length ? "Edit" : "Set"} dose timing for ${name}`}>
            {ordered.length ? "Edit" : "Set timing"}
          </button>
        )}
      </div>

      {editing ? (
        <DoseRuleEditor
          medication={{ ...medication, dose_rules: rules }}
          patient={patient}
          onCancel={() => setEditing(false)}
          onSaved={(updated) => {
            setEditing(false);
            onUpdated(updated);
          }}
        />
      ) : ordered.length > 0 ? (
        <ol className="pv-timing-summary">
          {ordered.map((rule) => (
            <li key={rule.id} className="pv-timing-summary-item">
              <span className="pv-timing-seq" aria-hidden="true">{rule.sequence}</span>
              <span className="pv-timing-summary-text">
                <span className="sr-only">Dose {rule.sequence}: </span>
                {describeRule(rule)}
                {rule.dose ? <span className="pv-timing-override"> · {rule.dose}</span> : null}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="pv-timing-empty">Not set. Add timing to schedule doses around meals or at set times.</p>
      )}
    </section>
  );
}

export function MedicationList({
  medications,
  loading,
  error,
  showHeading = true,
  patient = null,
  onMedicationUpdated,
}: {
  medications: MedicationResponse[];
  loading?: boolean;
  error?: string | null;
  /** Off when the surrounding DetailSheet already names the section. */
  showHeading?: boolean;
  /** Supplies the recorded routine the dose-timing editor refers to. */
  patient?: PatientResponse | null;
  /** Enables dose-timing editing. Omitted, cards stay read-only as before. */
  onMedicationUpdated?: (updated: MedicationResponse) => void;
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
          ? medications.map((medication, index) => {
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
                  id={`medication-${medication.id}`}
                  className={`pv-meds-card pv-meds-item ${active ? "" : "is-inactive"}`}
                >
                  <header className="pv-meds-record-header">
                    <span className="pv-meds-course-label">
                      <CapsuleIcon className="h-4 w-4" />
                      Course {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className={`pv-meds-status ${active ? "is-active" : ""}`}>
                      <span className="pv-meds-status-text">{medication.status.replace(/_/g, " ")}</span>
                    </span>
                  </header>
                  <div className="pv-meds-identity">
                    <h3 className={`pv-meds-name ${identityVerified || cached.cached ? "" : "is-unnamed"}`}>
                      {name}
                    </h3>
                    <dl className="pv-meds-dose-record">
                      <dt>Recorded dose</dt>
                      <dd>{medication.dose ?? "Not recorded"}</dd>
                    </dl>
                    {termType || genericContext || identityVerified ? (
                      <details className="pv-meds-catalog">
                        <summary>
                          Catalog details
                          {identityVerified ? <span className="pv-meds-verified"><CheckIcon className="pv-meds-verified-icon" /><span>Verified</span></span> : null}
                        </summary>
                        <p className="pv-meds-kind">{[termType, genericContext, medication.dose].filter(Boolean).join(" · ") || "Catalog identity verified"}</p>
                      </details>
                    ) : null}
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

                  {active && onMedicationUpdated ? (
                    <DoseTiming medication={medication} patient={patient} onUpdated={onMedicationUpdated} />
                  ) : null}
                </article>
              );
            })
          : null}
      </div>
    </section>
  );
}
