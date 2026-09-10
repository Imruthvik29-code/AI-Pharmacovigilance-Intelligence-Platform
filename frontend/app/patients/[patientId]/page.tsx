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
import { PatientWorkspaceCards, type WorkspaceCardId } from "@/components/PatientWorkspaceCards";
import { PatientAvatar } from "@/components/PatientAvatar";
import { SchedulePanel } from "@/components/SchedulePanel";
import { StatusBanner } from "@/components/StatusBanner";
import { SymptomPanel } from "@/components/SymptomPanel";
import { TimelineList } from "@/components/TimelineList";
import { listAnalysisRuns, runAnalysis } from "@/lib/api/analysis";
import { ApiError } from "@/lib/api/errors";
import { listMedications } from "@/lib/api/medications";
import { getPatient } from "@/lib/api/patients";
import { listSymptoms } from "@/lib/api/symptoms";
import { listTimeline } from "@/lib/api/timeline";
import { usePageTitle } from "@/lib/hooks/usePageTitle";
import { primaryButtonClass, secondaryButtonClass } from "@/lib/ui/classes";
import type { AnalysisRunResponse, MedicationResponse, PatientResponse, SymptomResponse, TimelineEventResponse } from "@/lib/api/types";

export default function PatientPage() {
  const params = useParams<{ patientId: string }>();
  const patientId = params.patientId;
  const [patient, setPatient] = useState<PatientResponse | null>(null);
  const [medications, setMedications] = useState<MedicationResponse[]>([]);
  const [symptoms, setSymptoms] = useState<SymptomResponse[]>([]);
  const [timeline, setTimeline] = useState<TimelineEventResponse[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisRunResponse | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [pageError, setPageError] = useState<string | null>(null);
  const [medError, setMedError] = useState<string | null>(null);
  const [symptomsLoading, setSymptomsLoading] = useState(true);
  const [symptomsError, setSymptomsError] = useState<string | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisHistoryError, setAnalysisHistoryError] = useState<string | null>(null);
  const [analysisHistoryLoaded, setAnalysisHistoryLoaded] = useState(false);
  const [running, setRunning] = useState(false);
  const [detailSection, setDetailSection] = useState<WorkspaceCardId | null>(null);

  usePageTitle(patient?.name ?? "Patient");

  const refreshSecondary = useCallback(async (isCurrent: () => boolean = () => true, updateAnalysis = true) => {
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
      if (updateAnalysis && runs.length > 0) setAnalysis(runs[0]);
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
      setPatient(null);
      setMedications([]);
      setSymptoms([]);
      setTimeline([]);
      setAnalysis(null);
      setAnalysisHistoryLoaded(false);
      setAnalysisHistoryError(null);
      setSymptomsLoading(true);
      setPageError(null);
      setMedError(null);
      setSymptomsError(null);
      setTimelineError(null);
      setAnalysisError(null);
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
        try {
          const nextSymptoms = await listSymptoms(patientId);
          if (!cancelled) {
            setSymptoms(nextSymptoms);
            setSymptomsError(null);
          }
        } catch (err) {
          if (!cancelled) setSymptomsError(err instanceof ApiError ? err.detail : "Could not load symptoms.");
        } finally {
          if (!cancelled) setSymptomsLoading(false);
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
        if (!cancelled) {
          setLoading(false);
          setSymptomsLoading(false);
        }
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [patientId, loadAttempt, refreshSecondary]);

  async function handleRunAnalysis() {
    if (running) return;
    setRunning(true);
    setAnalysisError(null);
    try {
      const nextRun = await runAnalysis(patientId);
      setAnalysis(nextRun);
      setAnalysisHistoryError(null);
      setAnalysisHistoryLoaded(true);
      await refreshSecondary(() => true, false);
    } catch (err) {
      setAnalysisError(err instanceof ApiError ? err.detail : "Analysis request failed.");
    } finally {
      setRunning(false);
    }
  }

  function handleViewDetails(section: WorkspaceCardId) {
    setDetailSection(section);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const activeCount = medications.filter((medication) => medication.status === "active").length;
  const unresolvedSymptoms = symptoms.filter((symptom) => !symptom.resolved_date).length;

  return (
    <AuthGate>
      <AppShell>
        <Link href="/dashboard" className="patient-back-link">
          <span aria-hidden="true">←</span> Patients
        </Link>

        {loading ? <div className="mt-6 max-w-md"><LoadingSkeleton label="Loading patient" lines={4} /></div> : null}
        {pageError ? (
          <div className="mt-6 space-y-3">
            <StatusBanner tone="error" role="alert">{pageError}</StatusBanner>
            <button type="button" onClick={() => setLoadAttempt((attempt) => attempt + 1)} className={secondaryButtonClass}>Try again</button>
          </div>
        ) : null}

        {patient ? (
          <>
            <header className="patient-hero">
              <PatientAvatar patient={patient} size="lg" />
              <div className="patient-hero-copy">
                <p className="patient-hero-kicker">Patient record</p>
                <h1>{patient.name}</h1>
                <p>{[patient.age != null ? `${patient.age} yrs` : null, patient.sex].filter(Boolean).join(" · ") || "No demographics recorded"}</p>
                {patient.relation ? <span>{patient.relation === "Self" ? "My profile" : patient.relation}</span> : null}
              </div>
              {!detailSection ? <p className="patient-hero-note">A focused record for treatment, symptoms, and safety.</p> : null}
            </header>
            {!detailSection ? <PatientWorkspaceCards analysis={analysis} medications={medications} symptoms={symptoms} timeline={timeline} onViewDetails={handleViewDetails} onRunAnalysis={() => void handleRunAnalysis()} analysisRunning={running} /> : null}
            {detailSection ? <div className="mt-7 flex items-center justify-between"><button type="button" onClick={() => setDetailSection(null)} className="inline-flex min-h-11 items-center gap-2 rounded-full border border-line bg-card px-4 text-sm font-medium">← Overview</button><p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">Details</p></div> : null}

            {analysisError ? <div className="mt-4"><StatusBanner tone="error" role="alert">{analysisError}</StatusBanner></div> : null}

            {detailSection === "safety" ? <section id="safety" aria-labelledby="safety-heading" className="mt-8 scroll-mt-6 rounded-3xl border border-line bg-card p-4 shadow-[0_1px_2px_rgba(20,32,41,0.03)] sm:p-6">
              <div className="mb-5 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
                <div><p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">01 · Safety</p><h2 id="safety-heading" className="mt-1 text-xl font-semibold tracking-tight">Safety analysis</h2></div>
                <p className="text-xs text-muted">Deterministic findings with evidence-backed explanation</p>
              </div>
              <div className="mb-5 flex justify-end"><button type="button" onClick={() => void handleRunAnalysis()} disabled={running} className={primaryButtonClass}>{running ? "Running analysis…" : "Run analysis"}</button></div>
              <AnalysisHero run={analysis} historyError={analysisHistoryError} historyLoaded={analysisHistoryLoaded} running={running} />
            </section> : null}

            {detailSection === "medications" ? <section id="medications" aria-labelledby="medications-heading" className="mt-6 scroll-mt-6 rounded-3xl border border-line bg-card p-4 shadow-[0_1px_2px_rgba(20,32,41,0.03)] sm:p-6">
              <div className="mb-5 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
                <div><p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">02 · Treatment</p><h2 id="medications-heading" className="mt-1 text-xl font-semibold tracking-tight">Medications</h2></div>
                <p className="text-xs text-muted">{activeCount} active of {medications.length} recorded</p>
              </div>
              <div className="space-y-6">
                <MedicationList medications={medications} error={medError} />
                <div className="border-t border-line pt-5">
                  <button type="button" onClick={() => setShowPicker((open) => !open)} className={`${secondaryButtonClass} w-full justify-center sm:w-auto`}>{showPicker ? "Hide medication form" : "Add medication"}</button>
                  {showPicker ? <div className="mt-4"><MedicationPicker patientId={patientId} onCreated={(medication) => { setMedications((current) => [...current, medication]); setShowPicker(false); void refreshSecondary(); }} /></div> : null}
                </div>
              </div>
            </section> : null}

            {detailSection === "medications" ? <section aria-labelledby="schedule-heading" className="mt-6 rounded-3xl border border-line bg-card p-4 shadow-[0_1px_2px_rgba(20,32,41,0.03)] sm:p-6">
              <div className="mb-5 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
                <div><p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">03 · Adherence</p><h2 id="schedule-heading" className="mt-1 text-xl font-semibold tracking-tight">Dose schedule</h2></div>
                <p className="text-xs text-muted">Scheduled doses and adherence activity</p>
              </div>
              <SchedulePanel patientId={patientId} medications={medications} onTimelineRefresh={() => void refreshSecondary()} />
            </section> : null}

            {detailSection === "symptoms" ? <section id="symptoms" aria-labelledby="symptoms-heading" className="mt-6 scroll-mt-6 rounded-3xl border border-line bg-card p-4 shadow-[0_1px_2px_rgba(20,32,41,0.03)] sm:p-6">
              <div className="mb-5 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
                <div><p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">04 · Clinical signals</p><h2 id="symptoms-heading" className="mt-1 text-xl font-semibold tracking-tight">Symptoms</h2></div>
                <p className="text-xs text-muted">{unresolvedSymptoms} unresolved of {symptoms.length} recorded</p>
              </div>
              <SymptomPanel patientId={patientId} medications={medications} symptoms={symptoms} loading={symptomsLoading} error={symptomsError} onCreated={(symptom) => { setSymptoms((current) => [...current, symptom]); void refreshSecondary(); }} />
            </section> : null}

            {detailSection === "timeline" ? <section id="timeline" aria-labelledby="timeline-heading" className="mt-6 scroll-mt-6 rounded-3xl border border-line bg-card p-4 shadow-[0_1px_2px_rgba(20,32,41,0.03)] sm:p-6">
              <div className="mb-5 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
                <div><p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">05 · Activity</p><h2 id="timeline-heading" className="mt-1 text-xl font-semibold tracking-tight">Patient timeline</h2></div>
                <p className="text-xs text-muted">Recent patient activity</p>
              </div>
              <TimelineList events={timeline} error={timelineError} />
            </section> : null}
          </>
        ) : null}
      </AppShell>
    </AuthGate>
  );
}
