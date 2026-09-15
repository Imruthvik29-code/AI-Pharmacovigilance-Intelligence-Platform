"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api/errors";
import { generateMedicationSchedule, listUpcomingDoses, markDose } from "@/lib/api/schedule";
import type { DoseStatus, MedicationResponse, UpcomingDoseResponse } from "@/lib/api/types";
import { displayDrugName } from "@/lib/drugs/nameCache";
import { IconChip } from "@/components/ui/IconChip";
import { CheckIcon } from "@/components/icons/Icons";
import { StatusBanner } from "@/components/StatusBanner";

type Props = {
  patientId: string;
  medications: MedicationResponse[];
  onTimelineRefresh?: () => void;
};

const statusActions: Array<{ status: DoseStatus; label: string }> = [
  { status: "taken", label: "Taken" },
  { status: "skipped", label: "Skipped" },
  { status: "missed", label: "Missed" },
];

function doseDateLabel(dose: UpcomingDoseResponse): string {
  const scheduled = new Date(dose.scheduled_time);
  return Number.isNaN(scheduled.getTime())
    ? "Scheduled dose"
    : new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(scheduled);
}

/** Consecutive doses that share a calendar day, keeping the order they were returned in. */
function groupByDay(doses: UpcomingDoseResponse[]): Array<{ label: string; doses: UpcomingDoseResponse[] }> {
  const groups: Array<{ label: string; doses: UpcomingDoseResponse[] }> = [];
  for (const dose of doses) {
    const label = doseDateLabel(dose);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.doses.push(dose);
    else groups.push({ label, doses: [dose] });
  }
  return groups;
}

export function SchedulePanel({ patientId, medications, onTimelineRefresh }: Props) {
  const [doses, setDoses] = useState<UpcomingDoseResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyDoseId, setBusyDoseId] = useState<string | null>(null);
  const [generatingMedicationId, setGeneratingMedicationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const medicationNames = useMemo(() => new Map(medications.map((medication) => [medication.id, medication])), [medications]);

  const loadDoses = useCallback(async () => {
    setLoading(true);
    try {
      setDoses(await listUpcomingDoses(patientId));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not load upcoming doses.");
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    void loadDoses();
  }, [loadDoses]);

  async function handleGenerate(medicationId: string) {
    setGeneratingMedicationId(medicationId);
    setError(null);
    setNotice(null);
    try {
      await generateMedicationSchedule(medicationId);
      await loadDoses();
      setNotice("Schedule generated. Upcoming doses are now shown below.");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setNotice("A schedule already exists for this medication.");
        await loadDoses();
      } else {
        setError(err instanceof ApiError ? err.detail : "Could not generate the schedule.");
      }
    } finally {
      setGeneratingMedicationId(null);
    }
  }

  async function handleMark(dose: UpcomingDoseResponse, status: DoseStatus) {
    if (busyDoseId) return;
    setBusyDoseId(dose.id);
    setError(null);
    setNotice(null);
    try {
      await markDose(dose.id, { status });
      await loadDoses();
      onTimelineRefresh?.();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setNotice("This dose was already marked. The schedule has been refreshed.");
        await loadDoses();
        onTimelineRefresh?.();
      } else {
        setError(err instanceof ApiError ? err.detail : "Could not update this dose.");
      }
    } finally {
      setBusyDoseId(null);
    }
  }

  const schedulableMedications = medications.filter(
    (medication) => medication.status === "active" && medication.duration_days != null && (medication.times_per_day != null || medication.interval_hours != null),
  );

  return (
    <section aria-labelledby="schedule-heading" className="pv-meds-section">
      <header className="pv-meds-section-head">
        <div className="pv-meds-section-row">
          <h2 id="schedule-heading" className="pv-meds-section-title">What is due next</h2>
          <button type="button" onClick={() => void loadDoses()} disabled={loading} className="pv-meds-quiet-button">
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        <p className="pv-meds-section-note">Only future, unmarked doses for active medications appear here.</p>
      </header>

      <div className="pv-meds-stack">
        {error ? <StatusBanner tone="error" role="alert">{error}</StatusBanner> : null}
        {notice ? <StatusBanner tone="info">{notice}</StatusBanner> : null}

        {loading ? (
          <div className="pv-meds-card pv-meds-loading" aria-label="Loading schedule">
            {[1, 2, 3].map((item) => <div key={item} className="pv-meds-loading-line" />)}
          </div>
        ) : doses.length > 0 ? (
          groupByDay(doses).map((group, index) => (
            <div key={`${group.label}-${index}`} className="pv-dose-day">
              <p className="pv-dose-day-label">{group.label}</p>
              <ul className="pv-meds-card pv-dose-list">
                {group.doses.map((dose) => {
                  const medication = medicationNames.get(dose.medication_id);
                  return (
                    <DoseRow key={dose.id} dose={dose} medication={medication} busy={busyDoseId === dose.id} onMark={handleMark} />
                  );
                })}
              </ul>
            </div>
          ))
        ) : (
          <div className="pv-meds-card pv-meds-empty">
            <IconChip Icon={CheckIcon} surface="var(--mild-bg)" ink="var(--mild-fg)" size="md" />
            <div className="min-w-0">
              <h3 className="pv-meds-empty-title">No upcoming doses</h3>
              <p className="pv-meds-empty-text">Generate a schedule for an active medication with a duration and dosing frequency, or check back after the next dose is due.</p>
            </div>
          </div>
        )}

        {schedulableMedications.length > 0 ? (
          <div className="pv-meds-schedules">
            <div className="pv-meds-subhead">
              <p className="pv-meds-subhead-title">Medication schedules</p>
              <p className="pv-meds-section-note">Schedules are created once per medication.</p>
            </div>
            <ul className="pv-meds-card pv-meds-schedule-list">
              {schedulableMedications.map((medication) => {
                const drugLabel = displayDrugName(medication.drug_id);
                const label = medication.drug_name ?? drugLabel.name;
                return (
                  <li key={medication.id} className="pv-meds-schedule">
                    <div className="pv-meds-schedule-copy">
                      <p className={`pv-meds-schedule-name ${medication.drug_name || drugLabel.cached ? "" : "is-unnamed"}`}>{label}</p>
                      <p className="pv-meds-schedule-dose">{medication.dose ?? "Dose not recorded"}</p>
                    </div>
                    <button type="button" onClick={() => void handleGenerate(medication.id)} disabled={generatingMedicationId !== null} className="on-dark pv-meds-dark-button" aria-label={`Create schedule for ${label}`}>
                      {generatingMedicationId === medication.id ? "Creating…" : "Create schedule"}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function DoseRow({ dose, medication, busy, onMark }: { dose: UpcomingDoseResponse; medication?: MedicationResponse; busy: boolean; onMark: (dose: UpcomingDoseResponse, status: DoseStatus) => void }) {
  const scheduled = new Date(dose.scheduled_time);
  const validDate = !Number.isNaN(scheduled.getTime());
  const timeLabel = validDate ? new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(scheduled) : "";
  const medicationLabel = dose.drug_name || displayDrugName(medication?.drug_id ?? "").name;

  return (
    <li className="pv-dose">
      <div className="pv-dose-head">
        {timeLabel ? <p className="pv-dose-time">{timeLabel}</p> : null}
        <div className="pv-dose-copy">
          <p className="pv-dose-name">{medicationLabel}</p>
          <p className="pv-dose-amount">{dose.dose ?? medication?.dose ?? "Dose not recorded"}</p>
        </div>
      </div>
      <div className="pv-dose-actions" aria-label={`Update ${medicationLabel} dose status`}>
        {statusActions.map((action) => (
          <button key={action.status} type="button" onClick={() => onMark(dose, action.status)} disabled={busy} className={action.status === "taken" ? "on-dark pv-dose-action is-primary" : "pv-dose-action"} aria-label={`${action.label} ${medicationLabel} dose`}>
            {busy ? "…" : action.label}
          </button>
        ))}
      </div>
    </li>
  );
}
