"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api/errors";
import { generateMedicationSchedule, listUpcomingDoses, markDose } from "@/lib/api/schedule";
import type { DoseStatus, MedicationResponse, UpcomingDoseResponse } from "@/lib/api/types";
import { displayDrugName } from "@/lib/drugs/nameCache";
import { primaryButtonClass, secondaryButtonClass } from "@/lib/ui/classes";
import { IconChip } from "@/components/ui/IconChip";
import { CheckIcon, ClockIcon } from "@/components/icons/Icons";
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
    <section aria-labelledby="schedule-heading">
      <div className="flex flex-col gap-3 px-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-ink-3">Medication schedule</p>
          <h2 id="schedule-heading" className="mt-0.5 text-[1.0625rem] font-semibold tracking-[-0.01em] text-ink">What is due next</h2>
          <p className="mt-1 max-w-2xl text-[0.8125rem] leading-5 text-ink-2">Only future, unmarked doses for active medications appear here.</p>
        </div>
        <button type="button" onClick={() => void loadDoses()} disabled={loading} className={secondaryButtonClass}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="mt-3">
        {error ? <div className="mb-4"><StatusBanner tone="error" role="alert">{error}</StatusBanner></div> : null}
        {notice ? <div className="mb-4"><StatusBanner tone="info">{notice}</StatusBanner></div> : null}

        {loading ? (
          <div className="space-y-3" aria-label="Loading schedule">
            {[1, 2, 3].map((item) => <div key={item} className="h-16 animate-pulse rounded-md bg-surface-sunk" />)}
          </div>
        ) : doses.length > 0 ? (
          <div className="space-y-3">
            {doses.map((dose) => {
              const medication = medicationNames.get(dose.medication_id);
              return (
                <DoseRow key={dose.id} dose={dose} medication={medication} busy={busyDoseId === dose.id} onMark={handleMark} />
              );
            })}
          </div>
        ) : (
          <div className="rounded-md bg-surface-sunk px-5 py-8 text-center">
            <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-mild-surface text-mild">
              <CheckIcon className="h-5 w-5" />
            </span>
            <h3 className="mt-3 text-[0.9375rem] font-semibold text-ink">No upcoming doses</h3>
            <p className="mx-auto mt-1 max-w-md text-[0.875rem] leading-6 text-ink-2">Generate a schedule for an active medication with a duration and dosing frequency, or check back after the next dose is due.</p>
          </div>
        )}

        {schedulableMedications.length > 0 ? (
          <div className="mt-6 border-t border-hairline pt-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[0.9375rem] font-semibold text-ink">Medication schedules</p>
                <p className="mt-1 text-[0.75rem] text-ink-3">Schedules are created once per medication.</p>
              </div>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {schedulableMedications.map((medication) => {
                const drugLabel = displayDrugName(medication.drug_id);
                return (
                  <div key={medication.id} className="flex flex-col items-start gap-3 rounded-md bg-surface-sunk px-3.5 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0 max-w-full">
                      <p className="truncate text-[0.875rem] font-semibold text-ink">{drugLabel.name}</p>
                      <p className="mt-0.5 text-[0.75rem] text-ink-3">{medication.dose ?? "Dose not recorded"}</p>
                    </div>
                    <button type="button" onClick={() => void handleGenerate(medication.id)} disabled={generatingMedicationId !== null} className={primaryButtonClass} aria-label={`Create schedule for ${drugLabel.name}`}>
                      {generatingMedicationId === medication.id ? "Creating…" : "Create schedule"}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function DoseRow({ dose, medication, busy, onMark }: { dose: UpcomingDoseResponse; medication?: MedicationResponse; busy: boolean; onMark: (dose: UpcomingDoseResponse, status: DoseStatus) => void }) {
  const scheduled = new Date(dose.scheduled_time);
  const validDate = !Number.isNaN(scheduled.getTime());
  const dateLabel = validDate ? new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(scheduled) : "Scheduled dose";
  const timeLabel = validDate ? new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(scheduled) : "";
  const medicationLabel = dose.drug_name || displayDrugName(medication?.drug_id ?? "").name;

  return (
    <div className="rounded-md bg-surface px-4 py-4 shadow-[var(--e1)] sm:px-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <IconChip Icon={ClockIcon} surface="var(--medications-surface)" ink="var(--medications-ink)" size="sm" className="mt-0.5" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <p className="font-semibold tracking-[-0.01em] text-ink">{medicationLabel}</p>
              <span className="text-[0.75rem] text-ink-3">{dose.dose ?? medication?.dose ?? "Dose not recorded"}</span>
            </div>
            <p className="mt-1 text-[0.8125rem] text-ink-2">{dateLabel} · {timeLabel}</p>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2 lg:min-w-[300px]" aria-label={`Update ${medicationLabel} dose status`}>
          {statusActions.map((action) => (
            <button key={action.status} type="button" onClick={() => onMark(dose, action.status)} disabled={busy} className={action.status === "taken" ? primaryButtonClass : secondaryButtonClass} aria-label={`${action.label} ${medicationLabel} dose`}>
              {busy ? "…" : action.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
