"use client";

import { useRef, useState } from "react";
import type { PointerEvent } from "react";
import type { AnalysisRunResponse, MedicationResponse, SymptomResponse, TimelineEventResponse } from "@/lib/api/types";

export type WorkspaceCardId = "safety" | "medications" | "symptoms" | "timeline";
type Direction = "left" | "right";
type StatusItem = { label: string; value: string };

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

  function renderPrimary(index: number, className: string, hidden = false) {
    const section = sections[index];
    const statusItems = statusFor(section.id, analysis, medications, symptoms, timeline);
    const hasAnalysis = section.id !== "safety" || Boolean(analysis);
    return (
      <article className={`workspace-primary ${className}`} aria-labelledby={`workspace-${section.id}`} aria-hidden={hidden || undefined}>
        <WorkspaceCardIcon section={section} />
        <WorkspaceCardHeading section={section} />
        <WorkspaceCardSummary sectionId={section.id} hasAnalysis={hasAnalysis} />
        <WorkspaceCardStatusList items={statusItems} />
        {hidden ? null : <WorkspaceCardAction section={section} hasAnalysis={hasAnalysis} onViewDetails={onViewDetails} onRunAnalysis={onRunAnalysis} analysisRunning={analysisRunning} />}
      </article>
    );
  }

  return (
    <section className="workspace-deck" aria-label="Patient workspace">
      <div className="workspace-card-stage" onPointerDown={handlePointerDown} onPointerUp={handlePointerUp} onPointerCancel={() => { pointerStart.current = null; }}>
        <div className="workspace-card-shadow workspace-card-shadow-one" aria-hidden="true" />
        <div className="workspace-card-shadow workspace-card-shadow-two" aria-hidden="true" />
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

function WorkspaceCardIcon({ section }: { section: typeof sections[number] }) {
  return <span className={`workspace-section-icon workspace-section-icon-${section.id}`} aria-hidden="true">{section.icon}</span>;
}

function WorkspaceCardHeading({ section }: { section: typeof sections[number] }) {
  return <div className="workspace-card-heading">
    <p className="workspace-eyebrow">{section.number} / {sections.length}</p>
    <h2 id={`workspace-${section.id}`}>{section.label}</h2>
  </div>;
}

function WorkspaceCardSummary({ sectionId, hasAnalysis }: { sectionId: WorkspaceCardId; hasAnalysis: boolean }) {
  const summary = sectionId === "safety"
    ? hasAnalysis ? "Deterministic safety analysis is available for review." : "No safety analysis has been run yet. Your medication record is ready for deterministic interaction, ADR, and adherence analysis."
    : `Review the recorded ${sectionId} data for this patient.`;
  return <p className="workspace-card-summary">{summary}</p>;
}

function WorkspaceCardStatusList({ items }: { items: StatusItem[] }) {
  return <ul className="workspace-card-status-list" aria-label="Section status">
    {items.map((item) => <li key={item.label}><span aria-hidden="true">•</span><span>{item.label}</span><strong>{item.value}</strong></li>)}
  </ul>;
}

function WorkspaceCardAction({ section, hasAnalysis, onViewDetails, onRunAnalysis, analysisRunning }: {
  section: typeof sections[number]; hasAnalysis: boolean; onViewDetails?: (id: WorkspaceCardId) => void; onRunAnalysis?: () => void; analysisRunning: boolean;
}) {
  const runAnalysis = section.id === "safety" && !hasAnalysis;
  return <button type="button" className="workspace-primary-action" onClick={() => runAnalysis ? onRunAnalysis?.() : onViewDetails?.(section.id)} disabled={runAnalysis && (!onRunAnalysis || analysisRunning)}>
    <span>{runAnalysis ? (analysisRunning ? "Running analysis…" : "Run analysis") : `View ${section.label.toLowerCase()} details`}</span><span className="workspace-primary-action-arrow" aria-hidden="true">→</span>
  </button>;
}

function statusFor(id: WorkspaceCardId, analysis: AnalysisRunResponse | null, medications: MedicationResponse[], symptoms: SymptomResponse[], timeline: TimelineEventResponse[]): StatusItem[] {
  if (id === "safety") return safetyStatus(analysis);
  if (id === "medications") return medicationStatus(medications);
  if (id === "symptoms") return symptomStatus(symptoms);
  return [{ label: "Timeline events", value: String(timeline.length) }];
}

function safetyStatus(analysis: AnalysisRunResponse | null): StatusItem[] {
  if (!analysis) return [{ label: "Analysis status", value: "Not analyzed" }];
  const findings = getFindingCount(analysis);
  const risk = analysis.risk_level ? `${analysis.risk_level[0].toUpperCase()}${analysis.risk_level.slice(1)} risk` : "Recorded";
  return [
    { label: "Safety findings", value: String(findings) },
    { label: "Risk level", value: risk },
    ...(analysis.created_at ? [{ label: "Last analysis", value: new Date(analysis.created_at).toLocaleString() }] : []),
  ];
}
function medicationStatus(medications: MedicationResponse[]): StatusItem[] {
  const active = medications.filter((medication) => medication.status === "active").length;
  const verified = medications.filter((medication) => Boolean(medication.drug_name)).length;
  return [{ label: "Active medications", value: String(active) }, { label: "Medications recorded", value: String(medications.length) }, { label: "Verified identities", value: String(verified) }];
}
function symptomStatus(symptoms: SymptomResponse[]): StatusItem[] {
  const unresolved = symptoms.filter((symptom) => !symptom.resolved_date).length;
  return [{ label: "Unresolved symptoms", value: String(unresolved) }, { label: "Symptoms recorded", value: String(symptoms.length) }];
}
function getFindingCount(analysis: AnalysisRunResponse): number {
  const result = analysis.deterministic_result;
  if (!result || typeof result !== "object") return 0;
  const interaction = "interaction_findings" in result && Array.isArray(result.interaction_findings) ? result.interaction_findings.length : 0;
  const adr = "adr_findings" in result && Array.isArray(result.adr_findings) ? result.adr_findings.length : 0;
  return interaction + adr;
}
