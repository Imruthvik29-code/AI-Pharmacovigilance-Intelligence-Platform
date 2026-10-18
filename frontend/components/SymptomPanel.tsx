"use client";

import { useId, useState } from "react";
import { ApiError } from "@/lib/api/errors";
import { createSymptom } from "@/lib/api/symptoms";
import type { MedicationResponse, SymptomResponse, SymptomSeverity } from "@/lib/api/types";
import { localCalendarDate } from "@/lib/dates/localDate";
import { displayDrugName } from "@/lib/drugs/nameCache";
import { unresolvedSymptomCount } from "@/lib/patient/summaries";
import { fieldOnCardClass } from "@/lib/ui/classes";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { StatusBanner } from "@/components/StatusBanner";
import { IconChip } from "@/components/ui/IconChip";
import { SeverityPill } from "@/components/ui/SeverityPill";
import { PlusIcon, PulseIcon } from "@/components/icons/Icons";

const severityOptions: SymptomSeverity[] = ["mild", "moderate", "severe"];

/** A recorded calendar date ("YYYY-MM-DD"), shown without any timezone shift. */
function formatCalendarDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** The local date of a recorded instant (an ISO timestamp). */
function formatRecordedDate(value: string): string {
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return value;
  return instant.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/**
 * The API lists symptoms by onset, then by when they were recorded. The screen
 * reads that same order newest first, so a symptom reported in this session
 * lands where a reload would put it.
 */
export function newestOnsetFirst(symptoms: SymptomResponse[]): SymptomResponse[] {
  return [...symptoms].sort(
    (a, b) => b.onset_date.localeCompare(a.onset_date) || b.created_at.localeCompare(a.created_at),
  );
}

function medicationName(medication: MedicationResponse): string {
  return medication.drug_name ?? displayDrugName(medication.drug_id).name;
}

/** The linked medication's recorded name; never a raw id. */
function linkedMedicationName(medicationId: string, medications: MedicationResponse[]): string {
  const medication = medications.find((item) => item.id === medicationId);
  return medication ? medicationName(medication) : "Name not available";
}

export function SymptomPanel({
  patientId,
  medications,
  symptoms,
  loading,
  error,
  onCreated,
  onRetry,
}: {
  patientId: string;
  medications: MedicationResponse[];
  symptoms: SymptomResponse[];
  loading?: boolean;
  error?: string | null;
  onCreated: (symptom: SymptomResponse) => void;
  /** Requests the symptom list again after a failed load. */
  onRetry?: () => void;
}) {
  const headingId = useId();
  const reportBodyId = useId();
  const [reporting, setReporting] = useState(false);
  const ready = !loading && !error;
  const unresolved = unresolvedSymptomCount(symptoms);

  return (
    <div className="pv-symptoms">
      <section className="pv-symptoms-section" aria-labelledby={headingId}>
        <header className="pv-symptoms-section-head">
          <p className="pv-detail-kicker">Patient-reported history</p>
          <div className="pv-symptoms-section-row">
            <h2 id={headingId} className="pv-symptoms-section-title">Recorded symptoms</h2>
            {ready && symptoms.length > 0 ? (
              <span className="pv-symptoms-count">
                {unresolved} unresolved of {symptoms.length} reported
              </span>
            ) : null}
          </div>
          {ready && symptoms.length > 1 ? (
            <p className="pv-symptoms-section-note">Most recent onset first.</p>
          ) : null}
        </header>

        <div className="pv-symptoms-list">
          {loading ? <LoadingSkeleton label="Loading symptoms" lines={3} /> : null}

          {!loading && error ? (
            <div className="pv-symptoms-alert" role="alert">
              <p className="pv-symptoms-alert-text">{error}</p>
              {onRetry ? (
                <button type="button" onClick={onRetry} className="pv-symptoms-retry">
                  Try again
                </button>
              ) : null}
            </div>
          ) : null}

          {ready && symptoms.length === 0 ? (
            <div className="pv-symptoms-card pv-symptoms-empty">
              <IconChip Icon={PulseIcon} surface="var(--surface-2)" ink="var(--ink-3)" size="md" />
              <div className="min-w-0">
                <p className="pv-symptoms-empty-title">No symptoms recorded</p>
                <p className="pv-symptoms-empty-text">
                  Reported symptoms will stay in the patient record and appear in the timeline.
                </p>
              </div>
            </div>
          ) : null}

          {ready
            ? newestOnsetFirst(symptoms).map((symptom) => (
                <SymptomRecord key={symptom.id} symptom={symptom} medications={medications} />
              ))
            : null}
        </div>

      <section
        aria-label="Report a symptom"
        className={`pv-symptoms-report ${reporting ? "is-open" : ""}`}
      >
        <button
          type="button"
          onClick={() => setReporting((open) => !open)}
          aria-expanded={reporting}
          aria-controls={reporting ? reportBodyId : undefined}
          className="pv-symptoms-report-trigger"
        >
          <span className="pv-symptoms-report-chip" aria-hidden="true">
            <PlusIcon className="h-5 w-5" />
          </span>
          <span className="pv-symptoms-report-copy">
            <span className="pv-symptoms-report-title">
              {reporting ? "Hide symptom form" : "Report a symptom"}
            </span>
            {reporting ? null : (
              <span className="pv-symptoms-report-note" aria-hidden="true">
                Describe it, how severe it is and when it started
              </span>
            )}
          </span>
        </button>
        {reporting ? (
          <div id={reportBodyId} className="pv-symptoms-report-body">
            <SymptomReportForm
              patientId={patientId}
              medications={medications}
              onCreated={(symptom) => {
                onCreated(symptom);
                setReporting(false);
              }}
            />
          </div>
        ) : null}
      </section>
      </section>
    </div>
  );
}

function SymptomRecord({
  symptom,
  medications,
}: {
  symptom: SymptomResponse;
  medications: MedicationResponse[];
}) {
  const resolved = Boolean(symptom.resolved_date);

  return (
    <article className={`pv-symptoms-item ${resolved ? "is-resolved" : ""}`}>
      <div className="pv-symptoms-onset">
        <span>Onset</span>
        <time dateTime={symptom.onset_date}>{formatCalendarDate(symptom.onset_date)}</time>
      </div>
      <div className="pv-symptoms-record-body">
      <div className="pv-symptoms-item-head">
        <div className="pv-symptoms-identity">
          <h3 className="pv-symptoms-name">{symptom.description}</h3>
          <div className="pv-symptoms-tags">
            <span className="pv-symptoms-severity">
              <span className="pv-symptoms-severity-label">Reported severity: </span>
              <SeverityPill severity={symptom.severity} />
            </span>
            <span className={`pv-symptoms-status ${resolved ? "" : "is-ongoing"}`}>
              {resolved ? "Resolved" : "Ongoing"}
            </span>
          </div>
        </div>
      </div>

      <dl className="pv-symptoms-facts">
        {symptom.resolved_date ? (
          <div className="pv-symptoms-fact">
            <dt>Resolved</dt>
            <dd>{formatCalendarDate(symptom.resolved_date)}</dd>
          </div>
        ) : null}
        <div className="pv-symptoms-fact">
          <dt>Reported</dt>
          <dd>{formatRecordedDate(symptom.created_at)}</dd>
        </div>
        {symptom.medication_id ? (
          <div className="pv-symptoms-fact pv-symptoms-fact-wide">
            <dt>Related medication</dt>
            <dd>{linkedMedicationName(symptom.medication_id, medications)}</dd>
          </div>
        ) : null}
      </dl>
      </div>
    </article>
  );
}

function SymptomReportForm({
  patientId,
  medications,
  onCreated,
}: {
  patientId: string;
  medications: MedicationResponse[];
  onCreated: (symptom: SymptomResponse) => void;
}) {
  const descriptionId = useId();
  const counterId = useId();
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
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : "Could not report symptom.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="pv-symptoms-form">
      <div>
        <label className="pv-symptoms-label" htmlFor={descriptionId}>What are you experiencing?</label>
        <textarea
          id={descriptionId}
          required
          minLength={1}
          maxLength={2000}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Describe the symptom in your own words"
          aria-describedby={counterId}
          className={`${fieldOnCardClass} pv-symptoms-field pv-symptoms-textarea`}
        />
        <p id={counterId} className="pv-symptoms-counter">{description.length}/2000</p>
      </div>

      <div className="pv-symptoms-form-grid">
        <div>
          <label className="pv-symptoms-label" htmlFor={severityId}>Severity</label>
          <select
            id={severityId}
            value={severity}
            onChange={(event) => setSeverity(event.target.value as SymptomSeverity)}
            className={`${fieldOnCardClass} pv-symptoms-field`}
          >
            {severityOptions.map((option) => (
              <option key={option} value={option}>{option[0].toUpperCase() + option.slice(1)}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="pv-symptoms-label" htmlFor={onsetId}>Onset date</label>
          <input
            id={onsetId}
            type="date"
            required
            value={onsetDate}
            onChange={(event) => setOnsetDate(event.target.value)}
            className={`${fieldOnCardClass} pv-symptoms-field`}
          />
        </div>
      </div>

      <div>
        <label className="pv-symptoms-label" htmlFor={medicationId}>
          Related medication <span className="pv-symptoms-optional">(optional)</span>
        </label>
        <select
          id={medicationId}
          value={medication}
          onChange={(event) => setMedication(event.target.value)}
          className={`${fieldOnCardClass} pv-symptoms-field`}
        >
          <option value="">Not specified</option>
          {medications.map((item) => (
            <option key={item.id} value={item.id}>
              {medicationName(item)}{item.dose ? ` · ${item.dose}` : ""}
            </option>
          ))}
        </select>
        {medications.length === 0 ? (
          <p className="pv-symptoms-hint">No medications are recorded for this patient.</p>
        ) : null}
      </div>

      {submitError ? <StatusBanner tone="error" role="alert">{submitError}</StatusBanner> : null}
      <button type="submit" disabled={!description.trim() || submitting} className="on-dark pv-symptoms-submit">
        {submitting ? "Recording…" : "Report symptom"}
      </button>
    </form>
  );
}
