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
import { PatientFindingRow, PatientInformationRow, PatientInformationRows, PatientSectionDetail } from "@/components/PatientSectionDetail";
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
  const latestTimelineEvent = [...timeline].sort((a, b) => b.event_time.localeCompare(a.event_time))[0];
  const deterministicResult = analysis?.deterministic_result;
  const interactionCount = deterministicResult && "interaction_findings" in deterministicResult && Array.isArray(deterministicResult.interaction_findings) ? deterministicResult.interaction_findings.length : 0;
  const adrCount = deterministicResult && "adr_findings" in deterministicResult && Array.isArray(deterministicResult.adr_findings) ? deterministicResult.adr_findings.length : 0;

  return (
    <AuthGate>
      <AppShell>
        {!detailSection ? <Link href="/dashboard" className="patient-back-link">
          <span aria-hidden="true">←</span> Patients
        </Link> : null}

        {loading ? <div className="mt-6 max-w-md"><LoadingSkeleton label="Loading patient" lines={4} /></div> : null}
        {pageError ? (
          <div className="mt-6 space-y-3">
            <StatusBanner tone="error" role="alert">{pageError}</StatusBanner>
            <button type="button" onClick={() => setLoadAttempt((attempt) => attempt + 1)} className={secondaryButtonClass}>Try again</button>
          </div>
        ) : null}

        {patient ? (
          <>
            {!detailSection ? <header className="patient-hero">
              <PatientAvatar patient={patient} size="lg" />
              <div className="patient-hero-copy">
                <p className="patient-hero-kicker">Patient record</p>
                <h1>{patient.name}</h1>
                <p>{[patient.age != null ? `${patient.age} yrs` : null, patient.sex].filter(Boolean).join(" · ") || "No demographics recorded"}</p>
                {patient.relation ? <span>{patient.relation === "Self" ? "My profile" : patient.relation}</span> : null}
              </div>
              <p className="patient-hero-note">A focused record for treatment, symptoms, and safety.</p>
            </header> : null}
            {!detailSection ? <PatientWorkspaceCards analysis={analysis} medications={medications} symptoms={symptoms} timeline={timeline} onViewDetails={handleViewDetails} onRunAnalysis={() => void handleRunAnalysis()} analysisRunning={running} /> : null}

            {analysisError ? <div className="mt-4"><StatusBanner tone="error" role="alert">{analysisError}</StatusBanner></div> : null}

            {detailSection === "safety" ? <PatientSectionDetail eyebrow={`01 · ${patient.name}`} title="Safety analysis" description="Deterministic findings with evidence-backed explanation from the current medication record." onBack={() => setDetailSection(null)} action={<button type="button" onClick={() => void handleRunAnalysis()} disabled={running} className={`${primaryButtonClass} w-full justify-center sm:w-auto`}>{running ? "Running analysis…" : "Run analysis"}</button>}>
              <PatientInformationRows label="Safety summary">
                <PatientInformationRow label="Safety score" value={analysis?.safety_score ?? "Not analyzed"} />
                <PatientInformationRow label="Risk level" value={analysis?.risk_level ?? "Pending"} />
                <PatientInformationRow label="Last analysis" value={analysis ? new Date(analysis.created_at).toLocaleString() : "Never"} />
                <PatientInformationRow label="Analysis version" value={analysis?.analysis_version ?? "—"} />
              </PatientInformationRows>
              <div className="space-y-2" aria-label="Safety findings">
                <PatientFindingRow label="Drug interactions" detail="Interactions identified in the active medication record." value={interactionCount} tone={interactionCount ? "critical" : "positive"} />
                <PatientFindingRow label="Adverse drug reactions" detail="Known reaction signals identified by the analysis." value={adrCount} tone={adrCount ? "warning" : "positive"} />
              </div>
              <AnalysisHero run={analysis} historyError={analysisHistoryError} historyLoaded={analysisHistoryLoaded} running={running} />
            </PatientSectionDetail> : null}

            {detailSection === "medications" ? <PatientSectionDetail eyebrow={`02 · ${patient.name}`} title="Medications" description="Current treatments, medication details, and scheduled dose activity." onBack={() => setDetailSection(null)} action={<button type="button" onClick={() => setShowPicker((open) => !open)} className={`${primaryButtonClass} w-full justify-center sm:w-auto`}>{showPicker ? "Close medication form" : "Add medication"}</button>}>
              <PatientInformationRows label="Medication summary"><PatientInformationRow label="Active" value={activeCount} /><PatientInformationRow label="Total recorded" value={medications.length} /></PatientInformationRows>
              <div className="space-y-6">
                <MedicationList medications={medications} error={medError} />
                {showPicker ? <MedicationPicker patientId={patientId} onCreated={(medication) => { setMedications((current) => [...current, medication]); setShowPicker(false); void refreshSecondary(); }} /> : null}
              </div>
              <SchedulePanel patientId={patientId} medications={medications} onTimelineRefresh={() => void refreshSecondary()} />
            </PatientSectionDetail> : null}

            {detailSection === "symptoms" ? <PatientSectionDetail eyebrow={`03 · ${patient.name}`} title="Symptoms" description="Clinical signals recorded for this patient and their relationship to treatment." onBack={() => setDetailSection(null)}>
              <PatientInformationRows label="Symptom summary"><PatientInformationRow label="Unresolved" value={unresolvedSymptoms} /><PatientInformationRow label="Total recorded" value={symptoms.length} /></PatientInformationRows>
              <SymptomPanel patientId={patientId} medications={medications} symptoms={symptoms} loading={symptomsLoading} error={symptomsError} onCreated={(symptom) => { setSymptoms((current) => [...current, symptom]); void refreshSecondary(); }} />
            </PatientSectionDetail> : null}

            {detailSection === "timeline" ? <PatientSectionDetail eyebrow={`04 · ${patient.name}`} title="Patient timeline" description="A chronological view of medication, symptom, adherence, and analysis activity." onBack={() => setDetailSection(null)}>
              <PatientInformationRows label="Timeline summary"><PatientInformationRow label="Total events" value={timeline.length} /><PatientInformationRow label="Latest activity" value={latestTimelineEvent ? new Date(latestTimelineEvent.event_time).toLocaleString() : "No activity"} /></PatientInformationRows>
              <TimelineList events={timeline} error={timelineError} />
            </PatientSectionDetail> : null}
          </>
        ) : null}
      </AppShell>
    </AuthGate>
  );
}
