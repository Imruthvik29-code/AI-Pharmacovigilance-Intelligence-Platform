"use client";

import { useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import type {
  AnalysisRunResponse,
  MedicationResponse,
  SymptomResponse,
  TimelineEventResponse,
} from "@/lib/api/types";

export type WorkspaceCardId = "safety" | "medications" | "symptoms" | "timeline";

type Props = {
  analysis: AnalysisRunResponse | null;
  medications: MedicationResponse[];
  symptoms: SymptomResponse[];
  timeline: TimelineEventResponse[];
  onViewDetails?: (id: WorkspaceCardId) => void;
  onRunAnalysis?: () => void;
  analysisRunning?: boolean;
};

const sections: Array<{ id: WorkspaceCardId; label: string; icon: string }> = [
  { id: "safety", label: "Safety", icon: "⌁" },
  { id: "medications", label: "Medications", icon: "+" },
  { id: "symptoms", label: "Symptoms", icon: "◌" },
  { id: "timeline", label: "Timeline", icon: "◷" },
];

export function PatientWorkspaceCards({
  analysis,
  medications,
  symptoms,
  timeline,
  onViewDetails,
  onRunAnalysis,
  analysisRunning = false,
}: Props) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [direction, setDirection] = useState<"forward" | "backward">("forward");
  const pointerStart = useRef<number | null>(null);
  const active = sections[activeIndex];

  function select(index: number) {
    if (index < 0 || index >= sections.length || index === activeIndex) return;
    setDirection(index > activeIndex ? "forward" : "backward");
    setActiveIndex(index);
  }

  function handlePointerDown(event: PointerEvent<HTMLElement>) {
    if (event.target instanceof HTMLElement && event.target.closest("button, a")) return;
    pointerStart.current = event.clientX;
  }

  function handlePointerUp(event: PointerEvent<HTMLElement>) {
    if (pointerStart.current === null) return;
    const delta = event.clientX - pointerStart.current;
    pointerStart.current = null;
    if (Math.abs(delta) < 44) return;
    select(activeIndex + (delta < 0 ? 1 : -1));
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      select(activeIndex + 1);
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      select(activeIndex - 1);
    }
  }

  return (
    <section className="workspace-deck" aria-label="Patient workspace">
      <div
        className="workspace-card-stage"
        role="group"
        aria-roledescription="carousel"
        aria-label={`${active.label}, section ${activeIndex + 1} of ${sections.length}`}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerCancel={() => { pointerStart.current = null; }}
      >
        <article
          key={active.id}
          className={`workspace-primary workspace-enter-${direction}`}
          aria-labelledby={`workspace-${active.id}`}
        >
          <span className={`workspace-section-icon workspace-tone-${active.id}`} aria-hidden="true">
            {active.icon}
          </span>
          <div className="workspace-primary-copy">
            <h2 id={`workspace-${active.id}`}>{active.label}</h2>
            <p className="workspace-description">{descriptionFor(active.id)}</p>
            <div className="workspace-summary">
              {briefFor(active.id, analysis, medications, symptoms, timeline)}
            </div>
          </div>
          {active.id === "safety" && !analysis ? (
            <button
              type="button"
              className="workspace-primary-action"
              onClick={() => onRunAnalysis?.()}
              disabled={!onRunAnalysis || analysisRunning}
            >
              {analysisRunning ? "Running analysis…" : "Run analysis"}
              <span aria-hidden="true">→</span>
            </button>
          ) : (
            <button
              type="button"
              className="workspace-primary-action"
              onClick={() => onViewDetails?.(active.id)}
            >
              View details <span aria-hidden="true">→</span>
            </button>
          )}
        </article>

        <div className="workspace-companions" aria-label="Choose a patient section">
          <button type="button" className="sr-only" aria-label={`Open ${active.label}`} aria-current="true">
            Current section: {active.label}
          </button>
          {sections.filter((_, index) => index !== activeIndex).map((section) => (
            <button
              key={section.id}
              type="button"
              className={`workspace-companion workspace-tone-${section.id}`}
              onClick={() => select(sections.indexOf(section))}
              aria-label={`Open ${section.label}`}
            >
              <span className="workspace-companion-icon" aria-hidden="true">{section.icon}</span>
              <strong>{section.label}</strong>
            </button>
          ))}
        </div>
      </div>

      <div className="workspace-pagination" aria-label={`Section ${activeIndex + 1} of ${sections.length}`}>
        {sections.map((section, index) => (
          <span
            key={section.id}
            className={index === activeIndex ? "is-active" : ""}
            aria-hidden="true"
          />
        ))}
      </div>
    </section>
  );
}

function descriptionFor(id: WorkspaceCardId) {
  return {
    safety: "Review potential risks, interactions, and safety considerations.",
    medications: "Review medicines recorded for this patient.",
    symptoms: "Review symptoms and their resolution status.",
    timeline: "Review the patient’s recorded activity.",
  }[id];
}

function briefFor(
  id: WorkspaceCardId,
  analysis: AnalysisRunResponse | null,
  medications: MedicationResponse[],
  symptoms: SymptomResponse[],
  timeline: TimelineEventResponse[],
) {
  if (id === "safety") {
    if (!analysis) return <><strong>Analysis not run</strong><span>No safety analysis has been run yet.</span></>;
    const findings = getFindingCount(analysis);
    const risk = analysis.risk_level
      ? `${analysis.risk_level[0].toUpperCase()}${analysis.risk_level.slice(1)} risk`
      : "Analysis recorded";
    return <><strong>{findings === 0 ? "No safety findings" : `${findings} safety ${findings === 1 ? "finding" : "findings"}`}</strong><span>{risk}</span></>;
  }
  if (id === "medications") {
    const activeCount = medications.filter((medication) => medication.status === "active").length;
    return <><strong>{activeCount} active</strong><span>{medications.length} medications recorded</span></>;
  }
  if (id === "symptoms") {
    const unresolved = symptoms.filter((symptom) => !symptom.resolved_date).length;
    return <><strong>{unresolved} unresolved</strong><span>{symptoms.length} symptoms recorded</span></>;
  }
  return <><strong>{timeline.length} events</strong><span>{timeline.length ? "Review recent activity" : "No activity recorded"}</span></>;
}

function getFindingCount(analysis: AnalysisRunResponse) {
  const result = analysis.deterministic_result;
  if (!result || typeof result !== "object") return 0;
  const interactions = "interaction_findings" in result && Array.isArray(result.interaction_findings)
    ? result.interaction_findings.length
    : 0;
  const adrs = "adr_findings" in result && Array.isArray(result.adr_findings)
    ? result.adr_findings.length
    : 0;
  return interactions + adrs;
}
