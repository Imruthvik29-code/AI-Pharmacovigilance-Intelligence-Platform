"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AnalysisHero } from "@/components/AnalysisHero";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { MedicationList } from "@/components/MedicationList";
import { MedicationPicker } from "@/components/MedicationPicker";
import { SchedulePanel } from "@/components/SchedulePanel";
import { StatusBanner } from "@/components/StatusBanner";
import { TimelineList } from "@/components/TimelineList";
import { listAnalysisRuns, runAnalysis } from "@/lib/api/analysis";
import { ApiError } from "@/lib/api/errors";
import { listMedications } from "@/lib/api/medications";
import { getPatient } from "@/lib/api/patients";
import { listTimeline } from "@/lib/api/timeline";
import { usePageTitle } from "@/lib/hooks/usePageTitle";
import { primaryButtonClass, secondaryButtonClass } from "@/lib/ui/classes";
import type { AnalysisRunResponse, MedicationResponse, PatientResponse, TimelineEventResponse } from "@/lib/api/types";

export default function PatientPage() {
  const params = useParams<{ patientId: string }>();
  const patientId = params.patientId;
  const [patient, setPatient] = useState<PatientResponse | null>(null);
  const [medications, setMedications] = useState<MedicationResponse[]>([]);
  const [timeline, setTimeline] = useState<TimelineEventResponse[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisRunResponse | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [medError, setMedError] = useState<string | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisHistoryError, setAnalysisHistoryError] = useState<string | null>(null);
  const [analysisHistoryLoaded, setAnalysisHistoryLoaded] = useState(false);
  const [running, setRunning] = useState(false);

  usePageTitle(patient?.name ?? "Patient");

  const refreshSecondary = useCallback(async (isCurrent: () => boolean = () => true) => {
    try {
      const nextTimeline = await listTimeline(patientId);
      if (!isCurrent()) return;
      setTimeline(nextTimeline);
      setTimelineError(null);
    } catch (err) {
      if (!isCurrent()) return;
      setTimelineError(err instanceof ApiError ? err.detail : "Could not load timeline.");
    }
    try {
      const runs = await listAnalysisRuns(patientId);
      if (!isCurrent()) return;
      setAnalysis(runs[0] ?? null);
      setAnalysisHistoryError(null);
    } catch (err) {
      if (!isCurrent()) return;
      setAnalysisHistoryError(err instanceof ApiError ? err.detail : "Could not load analysis history.");
    } finally {
      if (isCurrent()) setAnalysisHistoryLoaded(true);
    }
  }, [patientId]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setPageError(null);
      try {
        const nextPatient = await getPatient(patientId);
        if (cancelled) return;
        setPatient(nextPatient);
        try {
          const nextMeds = await listMedications(patientId);
          if (!cancelled) {
            setMedications(nextMeds);
            setMedError(null);
          }
        } catch (err) {
          if (!cancelled) setMedError(err instanceof ApiError ? err.detail : "Could not load medications.");
        }
        await refreshSecondary(() => !cancelled);
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 401) {
            window.location.href = "/login";
            return;
          }
          setPageError(err instanceof ApiError ? err.detail : "Could not load patient.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [patientId, refreshSecondary]);

  async function handleRunAnalysis() {
    if (running) return;
    setRunning(true);
    setAnalysisError(null);
    try {
      const nextRun = await runAnalysis(patientId);
      setAnalysis(nextRun);
      setAnalysisHistoryError(null);
      setAnalysisHistoryLoaded(true);
      await refreshSecondary();
    } catch (err) {
      setAnalysisError(err instanceof ApiError ? err.detail : "Analysis request failed.");
    } finally {
      setRunning(false);
    }
  }

  const demographics = patient
    ? [
        patient.age != null ? `Age ${patient.age}` : null,
        patient.sex,
        patient.weight_kg != null ? `${formatWeightKg(patient.weight_kg)} kg` : null,
        patient.renal_flag ? "Renal flag" : null,
        patient.hepatic_flag ? "Hepatic flag" : null,
      ].filter(Boolean)
    : [];
  const activeCount = medications.filter((medication) => medication.status === "active").length;

  return (
    <AuthGate>
      <AppShell>
        <Link href="/dashboard" className="inline-flex items-center gap-1 text-xs font-medium text-muted transition-colors hover:text-accent">
          <span aria-hidden="true">←</span> Patients
        </Link>

        {loading ? (
          <div className="mt-6 max-w-md"><LoadingSkeleton label="Loading patient" lines={4} /></div>
        ) : null}
        {pageError ? (
          <div className="mt-6"><StatusBanner tone="error" role="alert">{pageError}</StatusBanner></div>
        ) : null}

        {patient ? (
          <>
            <header className="mt-5 overflow-hidden rounded-3xl border border-line bg-card shadow-[0_1px_2px_rgba(20,32,41,0.04)]">
              <div className="flex flex-col gap-6 px-5 py-6 sm:px-7 sm:py-7 lg:flex-row lg:items-end lg:justify-between">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
                    <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">Patient record</p>
                  </div>
                  <h1 className="mt-2 truncate text-3xl font-semibold tracking-tight sm:text-4xl">{patient.name}</h1>
                  <p className="mt-2 text-sm text-muted">
                    {demographics.length > 0 ? demographics.join(" · ") : "No demographics recorded"}
                  </p>
                </div>
                <div className="w-full lg:w-auto lg:min-w-[190px]">
                  <button type="button" onClick={() => void handleRunAnalysis()} disabled={running} className={`${primaryButtonClass} w-full bg-ink sm:w-auto lg:min-w-[190px]`}>
                    {running ? "Running analysis…" : "Run analysis"}
                  </button>
                  {activeCount < 2 ? (
                    <p className="mt-2 text-center text-[11px] leading-4 text-muted lg:text-right">
                      Two active medications are needed for interaction analysis.
                    </p>
                  ) : null}
                </div>
              </div>
              <div className="flex flex-wrap gap-2 border-t border-line bg-paper/35 px-5 py-3 sm:px-7">
                <span className="rounded-full bg-card px-2.5 py-1 text-[11px] text-muted">{medications.length} medications</span>
                <span className="rounded-full bg-card px-2.5 py-1 text-[11px] text-muted">{activeCount} active</span>
                {patient.renal_flag ? <span className="rounded-full bg-[#fdf6ec] px-2.5 py-1 text-[11px] font-medium text-moderate">Renal flag</span> : null}
                {patient.hepatic_flag ? <span className="rounded-full bg-[#fdf6ec] px-2.5 py-1 text-[11px] font-medium text-moderate">Hepatic flag</span> : null}
              </div>
            </header>

            {analysisError ? (
              <div className="mt-4"><StatusBanner tone="error" role="alert">{analysisError}</StatusBanner></div>
            ) : null}

            <div className="mt-8">
              <AnalysisHero run={analysis} historyError={analysisHistoryError} historyLoaded={analysisHistoryLoaded} running={running} />
            </div>

            <div className="mt-8">
              <SchedulePanel patientId={patientId} medications={medications} onTimelineRefresh={() => void refreshSecondary()} />
            </div>

            <div className="mt-8 grid gap-5 lg:grid-cols-[1.08fr_0.92fr]">
              <div className="space-y-3">
                <MedicationList medications={medications} error={medError} />
                <button type="button" onClick={() => setShowPicker((open) => !open)} className={`${secondaryButtonClass} w-full justify-center sm:w-auto`}>
                  {showPicker ? "Hide medication form" : "Add medication"}
                </button>
                {showPicker ? (
                  <MedicationPicker patientId={patientId} onCreated={(medication) => {
                    setMedications((current) => [...current, medication]);
                    setShowPicker(false);
                    void refreshSecondary();
                  }} />
                ) : null}
              </div>
              <TimelineList events={timeline} error={timelineError} />
            </div>
          </>
        ) : null}
      </AppShell>
    </AuthGate>
  );
}

function formatWeightKg(value: number): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(1);
}
