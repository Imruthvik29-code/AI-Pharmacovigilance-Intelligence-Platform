"use client";

import { useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import type { AnalysisRunResponse, MedicationResponse, SymptomResponse, TimelineEventResponse } from "@/lib/api/types";

export type WorkspaceCardId = "safety" | "medications" | "symptoms" | "timeline";
type Props = { analysis: AnalysisRunResponse | null; medications: MedicationResponse[]; symptoms: SymptomResponse[]; timeline: TimelineEventResponse[]; onViewDetails?: (id: WorkspaceCardId) => void; onRunAnalysis?: () => void; analysisRunning?: boolean };

const sections: Array<{ id: WorkspaceCardId; label: string; icon: string }> = [
  { id: "safety", label: "Safety", icon: "⌁" },
  { id: "medications", label: "Medications", icon: "＋" },
  { id: "symptoms", label: "Symptoms", icon: "◌" },
  { id: "timeline", label: "Timeline", icon: "◷" },
];
const TRANSITION_MS = 240;

export function PatientWorkspaceCards({ analysis, medications, symptoms, timeline, onViewDetails, onRunAnalysis, analysisRunning = false }: Props) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [moving, setMoving] = useState(false);
  const [direction, setDirection] = useState<"next" | "previous">("next");
  const pointerStart = useRef<number | null>(null);

  function select(index: number) {
    if (index < 0 || index >= sections.length || index === activeIndex || moving) return;
    setDirection(index > activeIndex ? "next" : "previous");
    setMoving(true);
    window.setTimeout(() => { setActiveIndex(index); setMoving(false); }, TRANSITION_MS);
  }
  function onPointerDown(event: PointerEvent<HTMLElement>) { if (!(event.target instanceof HTMLElement && event.target.closest("button, a"))) pointerStart.current = event.clientX; }
  function onPointerUp(event: PointerEvent<HTMLElement>) {
    if (pointerStart.current === null) return;
    const delta = event.clientX - pointerStart.current; pointerStart.current = null;
    if (Math.abs(delta) < 42) return;
    select(activeIndex + (delta < 0 ? 1 : -1));
  }
  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "ArrowRight") { event.preventDefault(); select(activeIndex + 1); }
    if (event.key === "ArrowLeft") { event.preventDefault(); select(activeIndex - 1); }
  }
  const active = sections[activeIndex];

  return <section className="workspace-deck" aria-label="Patient workspace">
    <div className="workspace-card-stage" role="group" aria-roledescription="carousel" aria-label={`${active.label} workspace card`} tabIndex={0} onKeyDown={onKeyDown} onPointerDown={onPointerDown} onPointerUp={onPointerUp} onPointerCancel={() => { pointerStart.current = null; }}>
      <article className={`workspace-primary workspace-current ${moving ? `workspace-slide-${direction}` : ""}`} aria-labelledby={`workspace-${active.id}`}>
        <span className={`workspace-section-icon workspace-section-icon-${active.id}`} aria-hidden="true">{active.icon}</span>
        <div className="workspace-primary-copy">
          <h2 id={`workspace-${active.id}`}>{active.label}</h2>
          <p className="workspace-description">{descriptionFor(active.id)}</p>
          <div className="workspace-facts">{briefFor(active.id, analysis, medications, symptoms, timeline)}</div>
        </div>
        {active.id === "safety" && !analysis ? <button type="button" className="workspace-primary-action" onClick={() => onRunAnalysis?.()} disabled={!onRunAnalysis || analysisRunning}>{analysisRunning ? "Running analysis…" : "Run analysis"}<span aria-hidden="true">→</span></button> : <button type="button" className="workspace-primary-action" onClick={() => onViewDetails?.(active.id)}>View {active.label.toLowerCase()} details<span aria-hidden="true">→</span></button>}
      </article>
      <nav className="workspace-section-rail" aria-label="Patient workspace sections">
        <button type="button" className="sr-only" aria-label={`Open ${active.label}`} aria-current="true" onClick={() => select(activeIndex)}>Current section: {active.label}</button>
        {sections.filter((_, index) => index !== activeIndex).map((section) => <button key={section.id} type="button" className={`workspace-section-button workspace-section-icon-${section.id}`} onClick={() => select(sections.indexOf(section))} disabled={moving} aria-label={`Open ${section.label}`}>
          <span className="workspace-rail-icon" aria-hidden="true">{section.icon}</span><span>{section.label}</span>
        </button>)}
      </nav>
    </div>
    <div className="workspace-pagination" aria-label={`Section ${activeIndex + 1} of ${sections.length}`}><span className="sr-only">Section {activeIndex + 1} of {sections.length}</span>{sections.map((section, index) => <span key={section.id} aria-hidden="true" className={index === activeIndex ? "is-active" : ""} />)}</div>
    <p className="workspace-gesture-hint">Swipe, use arrow keys, or select a section.</p>
  </section>;
}

function descriptionFor(id: WorkspaceCardId) { return ({ safety: "Review potential risks, interactions, and safety considerations.", medications: "Review medicines recorded for this patient.", symptoms: "Review symptoms and their current resolution status.", timeline: "Review the patient’s recorded activity." })[id]; }
function briefFor(id: WorkspaceCardId, analysis: AnalysisRunResponse | null, medications: MedicationResponse[], symptoms: SymptomResponse[], timeline: TimelineEventResponse[]) {
  if (id === "safety") { const findings = analysis ? getFindingCount(analysis) : 0; return <>{analysis ? <><p>{findings ? `${findings} safety ${findings === 1 ? "finding" : "findings"}` : "No safety findings"}</p><small>{analysis.risk_level ? `${analysis.risk_level[0].toUpperCase()}${analysis.risk_level.slice(1)} risk` : "Analysis recorded"}</small></> : <><p>Analysis not run</p><small>No safety analysis has been run yet.</small></>}</>; }
  if (id === "medications") { const active = medications.filter((m) => m.status === "active").length; return <><p>{active} active medication{active === 1 ? "" : "s"}</p><small>{medications.length} recorded</small></>; }
  if (id === "symptoms") { const open = symptoms.filter((s) => !s.resolved_date).length; return <><p>{open} unresolved symptom{open === 1 ? "" : "s"}</p><small>{symptoms.length} recorded</small></>; }
  return <><p>{timeline.length} timeline event{timeline.length === 1 ? "" : "s"}</p><small>{timeline.length ? "Review recent activity" : "No activity recorded"}</small></>;
}
function getFindingCount(analysis: AnalysisRunResponse) { const result = analysis.deterministic_result; if (!result || typeof result !== "object") return 0; return ("interaction_findings" in result && Array.isArray(result.interaction_findings) ? result.interaction_findings.length : 0) + ("adr_findings" in result && Array.isArray(result.adr_findings) ? result.adr_findings.length : 0); }
