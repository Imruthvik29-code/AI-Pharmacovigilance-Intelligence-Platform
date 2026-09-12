"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { AnalysisHero } from "@/components/AnalysisHero";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { MedicationList } from "@/components/MedicationList";
import { MedicationPicker } from "@/components/MedicationPicker";
import { SchedulePanel } from "@/components/SchedulePanel";
import { StatusBanner } from "@/components/StatusBanner";
import { SymptomPanel } from "@/components/SymptomPanel";
import { TimelineList } from "@/components/TimelineList";
import { CategoryTabs } from "@/components/patient/CategoryTabs";
import { DetailSheet } from "@/components/patient/DetailSheet";
import { PatientHero } from "@/components/patient/PatientHero";
import { PatientWorkspace } from "@/components/patient/PatientWorkspace";
import { isCategoryId, type CategoryId } from "@/components/patient/categories";
import { PillButton } from "@/components/ui/PillButton";
import { listAnalysisRuns, runAnalysis } from "@/lib/api/analysis";
import { ApiError } from "@/lib/api/errors";
import { listMedications } from "@/lib/api/medications";
import { getPatient } from "@/lib/api/patients";
import { listSymptoms } from "@/lib/api/symptoms";
import { listTimeline } from "@/lib/api/timeline";
import { usePageTitle } from "@/lib/hooks/usePageTitle";
import { secondaryButtonClass } from "@/lib/ui/classes";
import { activeMedicationCount, unresolvedSymptomCount } from "@/lib/patient/summaries";
import type {
  AnalysisRunResponse,
  MedicationResponse,
  PatientResponse,
  SymptomResponse,
  TimelineEventResponse,
} from "@/lib/api/types";

export default function PatientPageRoute() {
  return (
    <Suspense fallback={null}>
      <PatientPage />
    </Suspense>
  );
}

function PatientPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const params = useParams<{ patientId: string }>();
  const patientId = params.patientId;

  const rawCategory = searchParams.get("category");
  /** Present + valid → detail view. Absent or unknown → overview. */
  const openCategory: CategoryId | null = isCategoryId(rawCategory) ? rawCategory : null;

  const [previewCategory, setPreviewCategory] = useState<CategoryId>("safety");
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

  usePageTitle(patient?.name ?? "Patient");

  const refreshSecondary = useCallback(
    async (isCurrent: () => boolean = () => true, updateAnalysis = true) => {
      const [timelineResult, runsResult] = await Promise.allSettled([
        listTimeline(patientId),
        listAnalysisRuns(patientId),
      ]);
      if (!isCurrent()) return;

      if (timelineResult.status === "fulfilled") {
        setTimeline(timelineResult.value);
        setTimelineError(null);
      } else {
        const err = timelineResult.reason;
        setTimelineError(err instanceof ApiError ? err.detail : "Could not load timeline.");
      }

      if (runsResult.status === "fulfilled") {
        if (updateAnalysis && runsResult.value.length > 0) setAnalysis(runsResult.value[0]);
        setAnalysisHistoryError(null);
      } else {
        const err = runsResult.reason;
        setAnalysisHistoryError(
          err instanceof ApiError ? err.detail : "Could not load analysis history.",
        );
      }
      setAnalysisHistoryLoaded(true);
    },
    [patientId],
  );

  useEffect(() => {
    let cancelled = false;
    const isCurrent = () => !cancelled;

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

        // Independent resources load together rather than in a waterfall.
        const [medsResult, symptomsResult] = await Promise.allSettled([
          listMedications(patientId),
          listSymptoms(patientId),
        ]);
        if (cancelled) return;

        if (medsResult.status === "fulfilled") {
          setMedications(medsResult.value);
          setMedError(null);
        } else {
          const err = medsResult.reason;
          setMedError(err instanceof ApiError ? err.detail : "Could not load medications.");
        }

        if (symptomsResult.status === "fulfilled") {
          setSymptoms(symptomsResult.value);
          setSymptomsError(null);
        } else {
          const err = symptomsResult.reason;
          setSymptomsError(err instanceof ApiError ? err.detail : "Could not load symptoms.");
        }
        setSymptomsLoading(false);

        await refreshSecondary(isCurrent);
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
    return () => {
      cancelled = true;
    };
  }, [patientId, loadAttempt, refreshSecondary]);

  // Returning from a detail keeps that category previewed on the overview.
  useEffect(() => {
    if (openCategory) setPreviewCategory(openCategory);
  }, [openCategory]);

  async function handleRunAnalysis() {
    if (running) return;
    setRunning(true);
    setAnalysisError(null);
    try {
      const nextRun = await runAnalysis(patientId);
      setAnalysis(nextRun);
      setAnalysisHistoryError(null);
      setAnalysisHistoryLoaded(true);
      // Keep the run we just received; history may lag behind it.
      await refreshSecondary(() => true, false);
    } catch (err) {
      setAnalysisError(err instanceof ApiError ? err.detail : "Analysis request failed.");
    } finally {
      setRunning(false);
    }
  }

  function openDetail(id: CategoryId) {
    setShowPicker(false);
    router.push(`${pathname}?category=${id}`);
  }

  function backToOverview() {
    setShowPicker(false);
    router.push(pathname);
  }

  const workspaceData = { analysis, medications, symptoms, timeline };
  const activeCount = activeMedicationCount(medications);
  const unresolvedSymptoms = unresolvedSymptomCount(symptoms);

  return (
    <AuthGate>
      <AppShell bleed>
        {loading ? (
          <div className="px-4 pt-6 sm:px-6">
            <LoadingSkeleton label="Loading patient" lines={4} />
          </div>
        ) : null}

        {pageError ? (
          <div className="space-y-3 px-4 pt-6 sm:px-6">
            <StatusBanner tone="error" role="alert">
              {pageError}
            </StatusBanner>
            <button
              type="button"
              onClick={() => setLoadAttempt((attempt) => attempt + 1)}
              className={secondaryButtonClass}
            >
              Try again
            </button>
          </div>
        ) : null}

        {patient ? (
          <>
            <PatientHero
              patient={patient}
              variant={openCategory ? "compact" : "full"}
              back={
                openCategory
                  ? { label: "Back to overview", onClick: backToOverview }
                  : { label: "Back to patients", href: "/dashboard" }
              }
            />

            {analysisError ? (
              <div className="mt-4 px-4 sm:px-6">
                <StatusBanner tone="error" role="alert">
                  {analysisError}
                </StatusBanner>
              </div>
            ) : null}

            {openCategory ? (
              <div className="px-detail space-y-4">
                <CategoryTabs activeId={openCategory} onSelect={openDetail} />

                {openCategory === "safety" ? (
                  <DetailSheet
                    categoryId="safety"
                    title="Safety analysis"
                    meta="Deterministic findings from the interaction, ADR and adherence engines, explained in plain language."
                    footer={
                      <PillButton
                        onClick={() => void handleRunAnalysis()}
                        disabled={running}
                        busy={running}
                        width="block"
                      >
                        {running ? "Running analysis…" : "Run analysis"}
                      </PillButton>
                    }
                  >
                    <AnalysisHero
                      run={analysis}
                      historyError={analysisHistoryError}
                      historyLoaded={analysisHistoryLoaded}
                      running={running}
                    />
                  </DetailSheet>
                ) : null}

                {openCategory === "medications" ? (
                  <DetailSheet
                    categoryId="medications"
                    title="Medications"
                    meta={`${activeCount} active of ${medications.length} recorded, with the dose schedule and adherence activity.`}
                  >
                    <MedicationList medications={medications} error={medError} showHeading={false} />

                    <div className="border-t border-hairline pt-5">
                      <button
                        type="button"
                        onClick={() => setShowPicker((open) => !open)}
                        className={`${secondaryButtonClass} w-full justify-center sm:w-auto`}
                      >
                        {showPicker ? "Hide medication form" : "Add medication"}
                      </button>
                      {showPicker ? (
                        <div className="mt-4">
                          <MedicationPicker
                            patientId={patientId}
                            onCreated={(medication) => {
                              setMedications((current) => [...current, medication]);
                              setShowPicker(false);
                              void refreshSecondary();
                            }}
                          />
                        </div>
                      ) : null}
                    </div>

                    <div className="border-t border-hairline pt-5">
                      <SchedulePanel
                        patientId={patientId}
                        medications={medications}
                        onTimelineRefresh={() => void refreshSecondary()}
                      />
                    </div>
                  </DetailSheet>
                ) : null}

                {openCategory === "symptoms" ? (
                  <DetailSheet
                    categoryId="symptoms"
                    title="Symptoms"
                    meta={`${unresolvedSymptoms} unresolved of ${symptoms.length} reported.`}
                  >
                    <SymptomPanel
                      patientId={patientId}
                      medications={medications}
                      symptoms={symptoms}
                      loading={symptomsLoading}
                      error={symptomsError}
                      onCreated={(symptom) => {
                        setSymptoms((current) => [...current, symptom]);
                        void refreshSecondary();
                      }}
                      showHeading={false}
                    />
                  </DetailSheet>
                ) : null}

                {openCategory === "timeline" ? (
                  <DetailSheet
                    categoryId="timeline"
                    title="Patient timeline"
                    meta={`${timeline.length} recorded ${timeline.length === 1 ? "event" : "events"}, most recent first.`}
                  >
                    <TimelineList events={timeline} error={timelineError} showHeading={false} />
                  </DetailSheet>
                ) : null}
              </div>
            ) : (
              <PatientWorkspace
                activeId={previewCategory}
                onSelect={setPreviewCategory}
                onOpen={openDetail}
                onRunAnalysis={() => void handleRunAnalysis()}
                analysisRunning={running}
                data={workspaceData}
              />
            )}
          </>
        ) : null}
      </AppShell>
    </AuthGate>
  );
}
