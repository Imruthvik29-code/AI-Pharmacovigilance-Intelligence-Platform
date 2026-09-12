"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { AnalysisHero } from "@/components/AnalysisHero";
import { AuthGate } from "@/components/AuthGate";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { MedicationList } from "@/components/MedicationList";
import { MedicationPicker } from "@/components/MedicationPicker";
import { SchedulePanel } from "@/components/SchedulePanel";
import { StatusBanner } from "@/components/StatusBanner";
import { SymptomPanel } from "@/components/SymptomPanel";
import { TimelineList } from "@/components/TimelineList";
import { DetailScreen } from "@/components/patient/DetailScreen";
import { PatientCardStack } from "@/components/patient/PatientCardStack";
import { PatientHero } from "@/components/patient/PatientHero";
import { isCategoryId, type CategoryId } from "@/components/patient/categories";
import { PrimaryCTA } from "@/components/ui/PrimaryCTA";
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

const DETAIL_COPY: Record<CategoryId, { title: string; description: string }> = {
  safety: {
    title: "Safety",
    description:
      "Deterministic analysis of interactions, adverse drug reactions and adherence for this record, explained in plain language.",
  },
  medications: {
    title: "Medications",
    description: "Prescribed courses, the dose schedule and recorded adherence activity.",
  },
  symptoms: {
    title: "Symptoms",
    description: "Reported symptoms, their recorded severity and any linked medication.",
  },
  timeline: {
    title: "Timeline",
    description: "Every recorded event for this patient, most recent first.",
  },
};

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
  /** Present + valid → detail screen. Absent or unknown → overview. */
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

  // Returning from a detail leaves that category in front on the overview.
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

  const activeCount = activeMedicationCount(medications);
  const unresolvedSymptoms = unresolvedSymptomCount(symptoms);

  return (
    <AuthGate>
      <div className="pv-canvas flex min-h-screen flex-col">
        {loading ? (
          <div className="px-4 pt-8 sm:px-6">
            <LoadingSkeleton label="Loading patient" lines={4} />
          </div>
        ) : null}

        {pageError ? (
          <div className="space-y-3 px-4 pt-8 sm:px-6">
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

        {patient && openCategory ? (
          <DetailScreen
            categoryId={openCategory}
            patient={patient}
            title={DETAIL_COPY[openCategory].title}
            description={DETAIL_COPY[openCategory].description}
            onBack={backToOverview}
            footer={
              openCategory === "safety" ? (
                <PrimaryCTA
                  onClick={() => void handleRunAnalysis()}
                  disabled={running}
                  busy={running}
                >
                  {running ? "Running analysis…" : "Run analysis"}
                </PrimaryCTA>
              ) : null
            }
          >
            {analysisError ? (
              <StatusBanner tone="error" role="alert">
                {analysisError}
              </StatusBanner>
            ) : null}

            {openCategory === "safety" ? (
              <AnalysisHero
                run={analysis}
                historyError={analysisHistoryError}
                historyLoaded={analysisHistoryLoaded}
                running={running}
              />
            ) : null}

            {openCategory === "medications" ? (
              <>
                <MedicationList medications={medications} error={medError} showHeading={false} />
                <div>
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
                <SchedulePanel
                  patientId={patientId}
                  medications={medications}
                  onTimelineRefresh={() => void refreshSecondary()}
                />
                <p className="pv-row-meta px-0.5">
                  {activeCount} active of {medications.length} recorded
                </p>
              </>
            ) : null}

            {openCategory === "symptoms" ? (
              <>
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
                <p className="pv-row-meta px-0.5">
                  {unresolvedSymptoms} unresolved of {symptoms.length} reported
                </p>
              </>
            ) : null}

            {openCategory === "timeline" ? (
              <TimelineList events={timeline} error={timelineError} showHeading={false} />
            ) : null}
          </DetailScreen>
        ) : null}

        {patient && !openCategory ? (
          <>
            <PatientHero patient={patient} backHref="/dashboard" backLabel="Back to patients" />
            <div className="pv-sheet flex-1">
              {analysisError ? (
                <div className="mb-4 px-4 sm:px-6">
                  <StatusBanner tone="error" role="alert">
                    {analysisError}
                  </StatusBanner>
                </div>
              ) : null}
              <PatientCardStack
                activeId={previewCategory}
                onSelect={setPreviewCategory}
                onOpen={openDetail}
                onRunAnalysis={() => void handleRunAnalysis()}
                analysisRunning={running}
                data={{ analysis, medications, symptoms, timeline }}
              />
            </div>
          </>
        ) : null}
      </div>
    </AuthGate>
  );
}
