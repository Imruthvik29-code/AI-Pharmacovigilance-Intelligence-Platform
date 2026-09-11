"use client";

import { useId, useState } from "react";
import { ApiError } from "@/lib/api/errors";
import { createSymptom } from "@/lib/api/symptoms";
import type { MedicationResponse, SymptomResponse, SymptomSeverity } from "@/lib/api/types";
import { localCalendarDate } from "@/lib/dates/localDate";
import { displayDrugName } from "@/lib/drugs/nameCache";
import { fieldClass, primaryButtonClass } from "@/lib/ui/classes";
import { StatusBanner } from "@/components/StatusBanner";

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

function severityClass(severity: SymptomSeverity): string {
  if (severity === "severe") return "border-high/30 bg-[#fdf0ef] text-high";
  if (severity === "moderate") return "border-moderate/30 bg-[#fdf6ec] text-moderate";
  return "border-accent/25 bg-[#eef6f4] text-accent";
}

export function SymptomPanel({
  patientId,
  medications,
  symptoms,
  loading,
  error,
  onCreated,
  embedded = false,
}: {
  patientId: string;
  medications: MedicationResponse[];
  symptoms: SymptomResponse[];
  loading?: boolean;
  error?: string | null;
  onCreated: (symptom: SymptomResponse) => void;
  embedded?: boolean;
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
    <section className={embedded ? "min-w-0" : "overflow-hidden rounded-2xl border border-line bg-card shadow-[0_1px_2px_rgba(20,32,41,0.04)]"} aria-label="Symptom management">
      {!embedded ? <div className="border-b border-line px-5 py-4">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">Patient report</p>
        <h2 className="mt-1 text-base font-semibold tracking-tight">Symptoms</h2>
        <p className="mt-1 text-xs leading-5 text-muted">Record a new symptom and, when known, the medication it may relate to.</p>
      </div> : null}

      <div className={`grid gap-6 lg:grid-cols-[0.9fr_1.1fr] ${embedded ? "" : "p-5"}`}>
        <div>
          <h3 className="mb-3 text-sm font-semibold text-ink">Record a symptom</h3>
          <form onSubmit={handleSubmit} className="rounded-xl border border-line bg-paper/45 p-4">
          <div>
            <label className="block text-sm font-medium" htmlFor={descriptionId}>What are you experiencing?</label>
            <textarea
              id={descriptionId}
              required
              minLength={1}
              maxLength={2000}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Describe the symptom in your own words"
              className={`${fieldClass} min-h-24 resize-y`}
            />
            <p className="mt-1 text-right text-[11px] text-muted">{description.length}/2000</p>
          </div>

          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium" htmlFor={severityId}>Severity</label>
              <select id={severityId} value={severity} onChange={(event) => setSeverity(event.target.value as SymptomSeverity)} className={fieldClass}>
                {severityOptions.map((option) => <option key={option} value={option}>{option[0].toUpperCase() + option.slice(1)}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium" htmlFor={onsetId}>Onset date</label>
              <input id={onsetId} type="date" required value={onsetDate} onChange={(event) => setOnsetDate(event.target.value)} className={fieldClass} />
            </div>
          </div>

          <div className="mt-3">
            <label className="block text-sm font-medium" htmlFor={medicationId}>Related medication <span className="font-normal text-muted">(optional)</span></label>
            <select id={medicationId} value={medication} onChange={(event) => setMedication(event.target.value)} className={fieldClass}>
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
            {medications.length === 0 ? <p className="mt-1 text-[11px] text-muted">No medications are recorded for this patient.</p> : null}
          </div>

          {submitError ? <div className="mt-3"><StatusBanner tone="error" role="alert">{submitError}</StatusBanner></div> : null}
          <button type="submit" disabled={!description.trim() || submitting} className={`${primaryButtonClass} mt-4 w-full justify-center`}>
            {submitting ? "Recording…" : "Report symptom"}
          </button>
          </form>
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold text-ink">Recorded symptoms</h3>
          {loading ? <p className="text-sm text-muted">Loading symptom history…</p> : null}
          {error ? <p className="text-sm text-high" role="alert">{error}</p> : null}
          {!loading && !error && symptoms.length === 0 ? (
            <div className="rounded-xl border border-dashed border-line bg-paper/60 px-4 py-6">
              <p className="text-sm font-medium">No symptoms recorded</p>
              <p className="mt-1 text-sm leading-6 text-muted">Reported symptoms will stay in the patient record and appear in the timeline.</p>
            </div>
          ) : null}
          {!loading && !error && symptoms.length > 0 ? (
            <div className="space-y-2">
              {[...symptoms].reverse().map((symptom) => (
                <article key={symptom.id} className="rounded-xl border border-line bg-paper/45 px-4 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <p className="min-w-0 flex-1 text-sm font-medium leading-5">{symptom.description}</p>
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${severityClass(symptom.severity)}`}>{symptom.severity}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted">
                    <span>Onset {formatDate(symptom.onset_date)}</span>
                    {symptom.resolved_date ? <span>Resolved {formatDate(symptom.resolved_date)}</span> : <span>Ongoing</span>}
                    {symptom.medication_id ? <span>Medication linked</span> : null}
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
