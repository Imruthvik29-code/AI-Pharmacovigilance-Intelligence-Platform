"use client";

import { useId, useState } from "react";
import { ApiError } from "@/lib/api/errors";
import { createSymptom } from "@/lib/api/symptoms";
import type { MedicationResponse, SymptomResponse, SymptomSeverity } from "@/lib/api/types";
import { localCalendarDate } from "@/lib/dates/localDate";
import { displayDrugName } from "@/lib/drugs/nameCache";
import { fieldOnSunkClass, primaryButtonClass } from "@/lib/ui/classes";
import { StatusBanner } from "@/components/StatusBanner";
import { IconChip } from "@/components/ui/IconChip";
import { SeverityPill } from "@/components/ui/SeverityPill";
import { PulseIcon } from "@/components/icons/Icons";

const severityOptions: SymptomSeverity[] = ["mild", "moderate", "severe"];

function formatDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function SymptomPanel({
  patientId,
  medications,
  symptoms,
  loading,
  error,
  onCreated,
  showHeading = true,
}: {
  patientId: string;
  medications: MedicationResponse[];
  symptoms: SymptomResponse[];
  loading?: boolean;
  error?: string | null;
  onCreated: (symptom: SymptomResponse) => void;
  /** Off when the surrounding DetailSheet already names the section. */
  showHeading?: boolean;
}) {
  const descriptionId = useId();
  const severityId = useId();
  const onsetId = useId();
  const medicationId = useId();
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState<SymptomSeverity>("mild");
  const [onsetDate, setOnsetDate] = useState(() => localCalendarDate());
  const [medication, setMedication] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = description.trim();
    if (!trimmed || submitting) return;

    setSubmitting(true);
    setSubmitError(null);
    try {
      const created = await createSymptom(patientId, {
        description: trimmed,
        severity,
        onset_date: onsetDate,
        medication_id: medication || null,
      });
      onCreated(created);
      setDescription("");
      setSeverity("mild");
      setOnsetDate(localCalendarDate());
      setMedication("");
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : "Could not report symptom.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section aria-label="Symptoms">
      {showHeading ? (
        <div className="px-1">
          <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-ink-3">Patient report</p>
          <h2 className="mt-0.5 text-[1.0625rem] font-semibold tracking-[-0.01em]">Symptoms</h2>
          <p className="mt-1 text-[0.8125rem] leading-5 text-ink-2">Record a new symptom and, when known, the medication it may relate to.</p>
        </div>
      ) : null}

      <div className={`${showHeading ? "mt-3" : ""} grid gap-4 lg:grid-cols-[0.9fr_1.1fr]`}>
        <form onSubmit={handleSubmit} className="rounded-md bg-surface-sunk p-4">
          <div>
            <label className="block text-[0.875rem] font-semibold" htmlFor={descriptionId}>What are you experiencing?</label>
            <textarea
              id={descriptionId}
              required
              minLength={1}
              maxLength={2000}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Describe the symptom in your own words"
              className={`${fieldOnSunkClass} min-h-24 resize-y`}
            />
            <p className="mt-1 text-right text-[0.6875rem] text-ink-3">{description.length}/2000</p>
          </div>

          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <label className="block text-[0.875rem] font-semibold" htmlFor={severityId}>Severity</label>
              <select id={severityId} value={severity} onChange={(event) => setSeverity(event.target.value as SymptomSeverity)} className={fieldOnSunkClass}>
                {severityOptions.map((option) => <option key={option} value={option}>{option[0].toUpperCase() + option.slice(1)}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[0.875rem] font-semibold" htmlFor={onsetId}>Onset date</label>
              <input id={onsetId} type="date" required value={onsetDate} onChange={(event) => setOnsetDate(event.target.value)} className={fieldOnSunkClass} />
            </div>
          </div>

          <div className="mt-3">
            <label className="block text-[0.875rem] font-semibold" htmlFor={medicationId}>Related medication <span className="font-normal text-ink-3">(optional)</span></label>
            <select id={medicationId} value={medication} onChange={(event) => setMedication(event.target.value)} className={fieldOnSunkClass}>
              <option value="">Not specified</option>
              {medications.map((item) => {
                const displayed = displayDrugName(item.drug_id);
                return (
                  <option key={item.id} value={item.id}>
                    {displayed.name}{item.dose ? ` · ${item.dose}` : ""}
                  </option>
                );
              })}
            </select>
            {medications.length === 0 ? <p className="mt-1 text-[0.6875rem] text-ink-3">No medications are recorded for this patient.</p> : null}
          </div>

          {submitError ? <div className="mt-3"><StatusBanner tone="error" role="alert">{submitError}</StatusBanner></div> : null}
          <button type="submit" disabled={!description.trim() || submitting} className={`${primaryButtonClass} mt-4 w-full justify-center`}>
            {submitting ? "Recording…" : "Report symptom"}
          </button>
        </form>

        <div>
          {loading ? <p className="text-[0.875rem] text-ink-2">Loading symptom history…</p> : null}
          {error ? <p className="rounded-md bg-severe-surface px-4 py-3 text-[0.875rem] text-severe" role="alert">{error}</p> : null}
          {!loading && !error && symptoms.length === 0 ? (
            <div className="rounded-md bg-surface-sunk px-4 py-6">
              <p className="text-[0.9375rem] font-semibold">No symptoms recorded</p>
              <p className="mt-1 text-[0.875rem] leading-6 text-ink-2">Reported symptoms will stay in the patient record and appear in the timeline.</p>
            </div>
          ) : null}
          {!loading && !error && symptoms.length > 0 ? (
            <div className="space-y-2">
              {[...symptoms].reverse().map((symptom) => (
                <article key={symptom.id} className="px-row items-start">
                  <IconChip Icon={PulseIcon} surface="var(--symptoms-surface)" ink="var(--symptoms-ink)" size="sm" />
                  <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <p className="min-w-0 flex-1 text-[0.875rem] font-medium leading-5">{symptom.description}</p>
                    <SeverityPill severity={symptom.severity} />
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[0.75rem] text-ink-3">
                    <span>Onset {formatDate(symptom.onset_date)}</span>
                    {symptom.resolved_date ? <span>Resolved {formatDate(symptom.resolved_date)}</span> : <span>Ongoing</span>}
                    {symptom.medication_id ? <span>Medication linked</span> : null}
                  </div>
                  </div>
                </article>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
