"use client";

import { useRef, useState } from "react";
import type { PointerEvent } from "react";
import type { AnalysisRunResponse, MedicationResponse, SymptomResponse, TimelineEventResponse } from "@/lib/api/types";

export type WorkspaceCardId = "safety" | "medications" | "symptoms" | "timeline";
type Direction = "left" | "right";

type Props = {
  analysis: AnalysisRunResponse | null;
  medications: MedicationResponse[];
  symptoms: SymptomResponse[];
  timeline: TimelineEventResponse[];
  onViewDetails?: (id: WorkspaceCardId) => void;
};

const sections: Array<{ id: WorkspaceCardId; number: string; label: string; shortLabel: string }> = [
  { id: "safety", number: "01", label: "Safety", shortLabel: "SAFETY" },
  { id: "medications", number: "02", label: "Medications", shortLabel: "MEDICATIONS" },
  { id: "symptoms", number: "03", label: "Symptoms", shortLabel: "SYMPTOMS" },
  { id: "timeline", number: "04", label: "Timeline", shortLabel: "TIMELINE" },
];

const TRANSITION_MS = 220;

export function PatientWorkspaceCards({ analysis, medications, symptoms, timeline, onViewDetails }: Props) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [transitionIndex, setTransitionIndex] = useState<number | null>(null);
  const [transitionDirection, setTransitionDirection] = useState<Direction | null>(null);
  const pointerStart = useRef<number | null>(null);
  const transitioning = transitionIndex != null && transitionDirection != null;

  const unresolvedSymptoms = symptoms.filter((symptom) => !symptom.resolved_date).length;
  const activeMedications = medications.filter((medication) => medication.status === "active").length;
  const findingCount = analysis ? getFindingCount(analysis) : 0;

  function select(index: number) {
    if (index < 0 || index >= sections.length || index === activeIndex || transitioning) return;

    const direction: Direction = index > activeIndex ? "left" : "right";
    setTransitionIndex(index);
    setTransitionDirection(direction);

    window.setTimeout(() => {
      setActiveIndex(index);
      setTransitionIndex(null);
      setTransitionDirection(null);
    }, TRANSITION_MS);
  }

  function handlePointerDown(event: PointerEvent<HTMLElement>) {
    const target = event.target;
    if (target instanceof HTMLElement && target.closest("button, a")) return;
    pointerStart.current = event.clientX;
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handlePointerUp(event: PointerEvent<HTMLElement>) {
    if (pointerStart.current == null) return;
    const delta = event.clientX - pointerStart.current;
    pointerStart.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (Math.abs(delta) < 48 || transitioning) return;

    if (delta < 0 && activeIndex < sections.length - 1) select(activeIndex + 1);
    if (delta > 0 && activeIndex > 0) select(activeIndex - 1);
  }

  function handlePointerCancel() {
    pointerStart.current = null;
  }

  function renderCard(index: number, className: string, isTransitionCard = false) {
    const section = sections[index];

    return (
      <article
        className={`workspace-card-active ${className}`}
        aria-labelledby={`workspace-${section.id}`}
        aria-hidden={isTransitionCard ? true : undefined}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">{section.number} · {section.label}</p>
            <h2 id={`workspace-${section.id}`} className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{section.label}</h2>
          </div>
          <span className="rounded-full border border-line px-2.5 py-1 text-[10px] font-mono text-muted">{index + 1} / {sections.length}</span>
        </div>

        <div className="mt-6 min-h-28">
          {section.id === "safety" ? <SafetyBrief analysis={analysis} findingCount={findingCount} /> : null}
          {section.id === "medications" ? <MedicationBrief medications={medications} activeCount={activeMedications} /> : null}
          {section.id === "symptoms" ? <SymptomBrief symptoms={symptoms} unresolvedCount={unresolvedSymptoms} /> : null}
          {section.id === "timeline" ? <TimelineBrief timeline={timeline} /> : null}
        </div>

        {!isTransitionCard ? (
          <button
            type="button"
            className="mt-6 inline-flex min-h-11 items-center justify-center rounded-full bg-ink px-5 py-2.5 text-sm font-medium text-white transition-transform hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
            onClick={() => onViewDetails?.(section.id)}
          >
            View details <span className="ml-2" aria-hidden="true">→</span>
          </button>
        ) : null}
      </article>
    );
  }

  return (
    <section aria-label="Patient workspace" className="mt-5">
      <div className="workspace-card-stack">
        <div
          className="workspace-card-stage"
          onPointerDown={handlePointerDown}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerCancel}
        >
          {transitioning ? (
            <>
              {renderCard(activeIndex, `workspace-card-exit-${transitionDirection}`, true)}
              {renderCard(transitionIndex, `workspace-card-enter-${transitionDirection}`, true)}
            </>
          ) : (
            renderCard(activeIndex, "workspace-card-current")
          )}
        </div>

        <div className="workspace-card-tabs" aria-label="Select patient workspace section">
          {sections.map((section, index) =>
            index === activeIndex ? null : (
              <button
                key={section.id}
                type="button"
                className="workspace-card-tab"
                onClick={() => select(index)}
                aria-label={`Open ${section.label}`}
                disabled={transitioning}
              >
                <span className="font-mono text-[9px] text-muted">{section.number}</span>
                <span className="workspace-card-tab-label">{section.shortLabel}</span>
              </button>
            ),
          )}
        </div>
      </div>
      <p className="mt-2 text-center text-[11px] text-muted sm:text-right">Tap a section tab or swipe to move through the workspace.</p>
    </section>
  );
}

function SafetyBrief({ analysis, findingCount }: { analysis: AnalysisRunResponse | null; findingCount: number }) {
  if (!analysis) {
    return <p className="max-w-xl text-sm leading-6 text-muted">No safety analysis has been run yet. The current medication record is ready for deterministic interaction, ADR and adherence analysis.</p>;
  }
  const risk = analysis.risk_level ? analysis.risk_level[0].toUpperCase() + analysis.risk_level.slice(1) : "Recorded";
  return (
    <div>
      <p className="text-3xl font-semibold tracking-tight">{risk} risk</p>
      <p className="mt-2 text-sm leading-6 text-muted">{findingCount === 0 ? "No interaction or ADR findings were recorded in this analysis." : `${findingCount} safety ${findingCount === 1 ? "finding" : "findings"} recorded in this analysis.`}</p>
      <p className="mt-3 text-[11px] text-muted">Analysis {new Date(analysis.created_at).toLocaleString()}</p>
    </div>
  );
}

function MedicationBrief({ medications, activeCount }: { medications: MedicationResponse[]; activeCount: number }) {
  const verified = medications.filter((medication) => Boolean(medication.drug_name)).length;
  return (
    <div>
      <p className="text-3xl font-semibold tracking-tight">{activeCount} active</p>
      <p className="mt-2 text-sm leading-6 text-muted">{medications.length} {medications.length === 1 ? "medication" : "medications"} recorded · {verified} verified {verified === 1 ? "identity" : "identities"}.</p>
    </div>
  );
}

function SymptomBrief({ symptoms, unresolvedCount }: { symptoms: SymptomResponse[]; unresolvedCount: number }) {
  const latest = [...symptoms].sort((a, b) => b.onset_date.localeCompare(a.onset_date))[0];
  return (
    <div>
      <p className="text-3xl font-semibold tracking-tight">{unresolvedCount} unresolved</p>
      <p className="mt-2 text-sm leading-6 text-muted">{symptoms.length} {symptoms.length === 1 ? "symptom" : "symptoms"} recorded{latest ? ` · latest: ${latest.description}` : ""}.</p>
    </div>
  );
}

function TimelineBrief({ timeline }: { timeline: TimelineEventResponse[] }) {
  const latest = [...timeline].sort((a, b) => b.event_time.localeCompare(a.event_time))[0];
  return (
    <div>
      <p className="text-3xl font-semibold tracking-tight">{timeline.length} recent events</p>
      <p className="mt-2 text-sm leading-6 text-muted">{latest ? latest.event_title : "No timeline activity has been recorded yet."}</p>
    </div>
  );
}

function getFindingCount(analysis: AnalysisRunResponse): number {
  const result = analysis.deterministic_result;
  if (!result || typeof result !== "object") return 0;
  const interaction = "interaction_findings" in result && Array.isArray(result.interaction_findings) ? result.interaction_findings.length : 0;
  const adr = "adr_findings" in result && Array.isArray(result.adr_findings) ? result.adr_findings.length : 0;
  return interaction + adr;
}
