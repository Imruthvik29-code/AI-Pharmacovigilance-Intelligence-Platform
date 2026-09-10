"use client";

import { useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import type { AnalysisRunResponse, MedicationResponse, SymptomResponse, TimelineEventResponse } from "@/lib/api/types";

export type WorkspaceCardId = "safety" | "medications" | "symptoms" | "timeline";
type Direction = "left" | "right";

type Props = {
  analysis: AnalysisRunResponse | null;
  medications: MedicationResponse[];
  symptoms: SymptomResponse[];
  timeline: TimelineEventResponse[];
  onViewDetails?: (id: WorkspaceCardId) => void;
  onRunAnalysis?: () => void;
  analysisRunning?: boolean;
};

const sections: Array<{ id: WorkspaceCardId; number: string; label: string; icon: string }> = [
  { id: "safety", number: "01", label: "Safety", icon: "⌁" },
  { id: "medications", number: "02", label: "Medications", icon: "＋" },
  { id: "symptoms", number: "03", label: "Symptoms", icon: "◌" },
  { id: "timeline", number: "04", label: "Timeline", icon: "◷" },
];
const TRANSITION_MS = 260;

export function PatientWorkspaceCards({ analysis, medications, symptoms, timeline, onViewDetails, onRunAnalysis, analysisRunning = false }: Props) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [transitionIndex, setTransitionIndex] = useState<number | null>(null);
  const [transitionDirection, setTransitionDirection] = useState<Direction | null>(null);
  const pointerStart = useRef<number | null>(null);
  const transitioning = transitionIndex !== null;

  function select(index: number) {
    if (index < 0 || index >= sections.length || index === activeIndex || transitioning) return;
    setTransitionIndex(index);
    setTransitionDirection(index > activeIndex ? "left" : "right");
    window.setTimeout(() => {
      setActiveIndex(index);
      setTransitionIndex(null);
      setTransitionDirection(null);
    }, TRANSITION_MS);
  }

  function handlePointerDown(event: PointerEvent<HTMLElement>) {
    if (event.target instanceof HTMLElement && event.target.closest("button, a")) return;
    pointerStart.current = event.clientX;
  }

  function handlePointerUp(event: PointerEvent<HTMLElement>) {
    if (pointerStart.current === null) return;
    const delta = event.clientX - pointerStart.current;
    pointerStart.current = null;
    if (Math.abs(delta) < 48 || transitioning) return;
    if (delta < 0) select(activeIndex + 1);
    if (delta > 0) select(activeIndex - 1);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (transitioning) return;
    const nextIndex = event.key === "ArrowRight" || event.key === "ArrowDown"
      ? activeIndex + 1
      : event.key === "ArrowLeft" || event.key === "ArrowUp"
        ? activeIndex - 1
        : event.key === "Home"
          ? 0
          : event.key === "End"
            ? sections.length - 1
            : null;
    if (nextIndex === null) return;
    event.preventDefault();
    select(Math.max(0, Math.min(sections.length - 1, nextIndex)));
  }

  function renderPrimary(index: number, className: string, hidden = false) {
    const section = sections[index];
    return (
      <article className={`workspace-primary ${className}`} data-workspace-card={section.id} aria-labelledby={`workspace-${section.id}`} aria-hidden={hidden || undefined}>
        <div className="workspace-primary-top">
          <span className={`workspace-section-icon workspace-section-icon-${section.id}`} aria-hidden="true">{section.icon}</span>
          <div>
            <p className="workspace-eyebrow">{section.number} / {sections.length}</p>
            <h2 id={`workspace-${section.id}`}>{section.label}</h2>
          </div>
        </div>
        <div className="workspace-primary-copy">{briefFor(section.id, analysis, medications, symptoms, timeline)}</div>
        {hidden ? null : section.id === "safety" && !analysis ? (
          <button type="button" className="workspace-primary-action" onClick={() => onRunAnalysis?.()} disabled={!onRunAnalysis || analysisRunning}>
            {analysisRunning ? "Running analysis…" : "Run analysis"}<span aria-hidden="true">→</span>
          </button>
        ) : (
          <button type="button" className="workspace-primary-action" onClick={() => onViewDetails?.(section.id)}>
            View {section.label.toLowerCase()} details <span aria-hidden="true">→</span>
          </button>
        )}
      </article>
    );
  }

  return (
    <section className="workspace-deck" aria-label="Patient workspace">
      <div className="workspace-card-stage" data-testid="workspace-card-stack" data-active-card={sections[activeIndex].id} tabIndex={0} role="group" aria-label="Workspace card stack" onKeyDown={handleKeyDown} onPointerDown={handlePointerDown} onPointerUp={handlePointerUp} onPointerCancel={() => { pointerStart.current = null; }}>
        <div className="workspace-card-shadow workspace-card-shadow-one" data-testid="workspace-companion-card" aria-hidden="true" />
        <div className="workspace-card-shadow workspace-card-shadow-two" data-testid="workspace-companion-card" aria-hidden="true" />
        {transitioning ? <>{renderPrimary(activeIndex, `workspace-exit-${transitionDirection}`, true)}{renderPrimary(transitionIndex!, `workspace-enter-${transitionDirection}`, true)}</> : renderPrimary(activeIndex, "workspace-current")}
      </div>
      <div className="workspace-section-rail" aria-label="Select patient workspace section">
        {sections.map((section, index) => (
          <button key={section.id} type="button" className={`workspace-section-button ${index === activeIndex ? "is-active" : ""}`} onClick={() => select(index)} disabled={transitioning} aria-label={`Open ${section.label}`} aria-current={index === activeIndex ? "true" : undefined}>
            <span className={`workspace-rail-icon workspace-section-icon-${section.id}`} aria-hidden="true">{section.icon}</span>
            <span><small>{section.number}</small><strong>{section.label}</strong></span>
            {index === activeIndex ? <span className="workspace-selected" aria-hidden="true">Selected</span> : <span aria-hidden="true">→</span>}
          </button>
        ))}
      </div>
      <p className="workspace-gesture-hint">Swipe the primary card, or choose a section below.</p>
    </section>
  );
}

function briefFor(id: WorkspaceCardId, analysis: AnalysisRunResponse | null, medications: MedicationResponse[], symptoms: SymptomResponse[], timeline: TimelineEventResponse[]) {
  if (id === "safety") return <SafetyBrief analysis={analysis} />;
  if (id === "medications") return <MedicationBrief medications={medications} />;
  if (id === "symptoms") return <SymptomBrief symptoms={symptoms} />;
  return <TimelineBrief timeline={timeline} />;
}

function SafetyBrief({ analysis }: { analysis: AnalysisRunResponse | null }) {
  if (!analysis) return <><p className="workspace-metric">Not analyzed</p><p>No safety analysis has been run yet. Your medication record is ready for deterministic interaction, ADR, and adherence analysis.</p></>;
  const findings = getFindingCount(analysis);
  const risk = analysis.risk_level ? `${analysis.risk_level[0].toUpperCase()}${analysis.risk_level.slice(1)} risk` : "Recorded";
  return <><p className="workspace-metric">{risk}</p><p>{findings === 0 ? "Analysis completed — no interaction or ADR findings recorded." : `${findings} safety ${findings === 1 ? "finding" : "findings"} recorded.`}</p><small>Last analysis {new Date(analysis.created_at).toLocaleString()}</small></>;
}
function MedicationBrief({ medications }: { medications: MedicationResponse[] }) {
  const active = medications.filter((medication) => medication.status === "active").length;
  const verified = medications.filter((medication) => Boolean(medication.drug_name)).length;
  return <><p className="workspace-metric">{active} active</p><p>{medications.length} medications recorded · {verified} verified identities</p></>;
}
function SymptomBrief({ symptoms }: { symptoms: SymptomResponse[] }) {
  const unresolved = symptoms.filter((symptom) => !symptom.resolved_date).length;
  const latest = [...symptoms].sort((a, b) => b.onset_date.localeCompare(a.onset_date))[0];
  return <><p className="workspace-metric">{unresolved} unresolved</p><p>{symptoms.length} symptoms recorded{latest ? ` · latest: ${latest.description}` : ""}</p></>;
}
function TimelineBrief({ timeline }: { timeline: TimelineEventResponse[] }) {
  const latest = [...timeline].sort((a, b) => b.event_time.localeCompare(a.event_time))[0];
  return <><p className="workspace-metric">{timeline.length} events</p><p>{latest ? `Latest: ${latest.event_title}` : "No timeline activity has been recorded yet."}</p></>;
}
function getFindingCount(analysis: AnalysisRunResponse): number {
  const result = analysis.deterministic_result;
  if (!result || typeof result !== "object") return 0;
  const interaction = "interaction_findings" in result && Array.isArray(result.interaction_findings) ? result.interaction_findings.length : 0;
  const adr = "adr_findings" in result && Array.isArray(result.adr_findings) ? result.adr_findings.length : 0;
  return interaction + adr;
}
