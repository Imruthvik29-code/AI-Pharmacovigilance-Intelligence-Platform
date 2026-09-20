"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/errors";
import { getPatient, updatePatient } from "@/lib/api/patients";
import type { PatientResponse } from "@/lib/api/types";
import { primaryButtonClass } from "@/lib/ui/classes";
import { StatusBanner } from "@/components/StatusBanner";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import {
  detectTimezone,
  EMPTY_ROUTINE,
  PatientRoutineFields,
  routineToPayload,
  toTimeInputValue,
  type RoutineDraft,
} from "@/components/PatientRoutineFields";

function draftFrom(patient: PatientResponse): RoutineDraft {
  return {
    // Only prefill from the device when nothing is stored yet; a saved
    // timezone belongs to the patient and must not be overwritten by
    // whatever device happens to be opening the form.
    timezone: patient.timezone ?? detectTimezone(),
    breakfast: toTimeInputValue(patient.breakfast_time),
    lunch: toTimeInputValue(patient.lunch_time),
    dinner: toTimeInputValue(patient.dinner_time),
  };
}

/**
 * Edits only the routine fields of an existing patient, through the
 * existing partial-update PUT. No other patient field is sent, so nothing
 * else on the record can be disturbed from here.
 */
export function PatientRoutineForm({ patientId }: { patientId: string }) {
  const [patient, setPatient] = useState<PatientResponse | null>(null);
  const [routine, setRoutine] = useState<RoutineDraft>(EMPTY_ROUTINE);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      try {
        const found = await getPatient(patientId);
        if (!active) return;
        setPatient(found);
        setRoutine(draftFrom(found));
        setLoadError(null);
      } catch (err) {
        if (!active) return;
        setLoadError(err instanceof ApiError ? err.detail : "Could not load this patient.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [patientId]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      const updated = await updatePatient(patientId, routineToPayload(routine));
      setPatient(updated);
      setRoutine(draftFrom(updated));
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.detail : "Could not save the daily routine.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingSkeleton label="Loading patient" lines={3} />;
  if (loadError) {
    return (
      <StatusBanner tone="error" role="alert">
        {loadError}
      </StatusBanner>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {patient ? (
        <div>
          <p className="pv-eyebrow">Daily routine</p>
          <h1 className="pv-section-title mt-0.5">{patient.name}</h1>
        </div>
      ) : null}

      <PatientRoutineFields value={routine} onChange={setRoutine} idPrefix="edit-routine" />

      {saveError ? (
        <StatusBanner tone="error" role="alert">
          {saveError}
        </StatusBanner>
      ) : null}
      {saved && !saveError ? <StatusBanner tone="info">Daily routine saved.</StatusBanner> : null}

      <button type="submit" disabled={saving} className={primaryButtonClass}>
        {saving ? "Saving…" : "Save routine"}
      </button>
    </form>
  );
}
