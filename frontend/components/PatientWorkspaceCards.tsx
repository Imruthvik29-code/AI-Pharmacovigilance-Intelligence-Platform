"use client";

import { useRef, useState } from "react";
import type { PointerEvent } from "react";
import type { AnalysisRunResponse, MedicationResponse, SymptomResponse, TimelineEventResponse } from "@/lib/api/types";

export type WorkspaceCardId = "safety" | "medications" | "symptoms" | "timeline";

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

export function PatientWorkspaceCards({ analysis, medications, symptoms, timeline, onViewDetails }: Props) {
  const [activeIndex, setActiveIndex] = useState(0);
  const pointerStart = useRef<number | null>(null);
  const active = sections[activeIndex];
  const unresolvedSymptoms = symptoms.filter((symptom) => !symptom.resolved_date).length;
  const activeMedications = medications.filter((medication) => medication.status === "active").length;
  const findingCount = analysis ? getFindingCount(analysis) : 0;

  function select(index: number) {
    setActiveIndex(Math.max(0, Math.min(sections.length - 1, index)));
  }
  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    pointerStart.current = event.clientX;
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function handlePointerUp(event: PointerEvent<HTMLDivElement>) {
    if (pointerStart.current == null) return;
    const delta = event.clientX - pointerStart.current;
    pointerStart.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (Math.abs(delta) < 48) return;
    if (delta < 0 && activeIndex < sections.length - 1) select(activeIndex + 1);
    if (delta > 0 && activeIndex > 0) select(activeIndex - 1);
  }

  return (
    <section aria-label="Patient workspace" className="mt-5">
      <div className="workspace-card-stack" onPointerDown={handlePointerDown} onPointerUp={handlePointerUp} onPointerCancel={() => { pointerStart.current = null; }}>
        <article className="workspace-card-active" aria-labelledby={`workspace-${active.id}`}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">{active.number} · {active.label}</p>
              <h2 id={`workspace-${active.id}`} className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{active.label}</h2>
            </div>
            <span className="rounded-full border border-line px-2.5 py-1 text-[10px] font-mono text-muted">{activeIndex + 1} / {sections.length}</span>
          </div>
          <div className="mt-6 min-h-28">
            {active.id === "safety" ? <SafetyBrief analysis={analysis} findingCount={findingCount} /> : null}
            {active.id === "medications" ? <MedicationBrief medications={medications} activeCount={activeMedications} /> : null}
            {active.id === "symptoms" ? <SymptomBrief symptoms={symptoms} unresolvedCount={unresolvedSymptoms} /> : null}
            {active.id === "timeline" ? <TimelineBrief timeline={timeline} /> : null}
          </div>
          <button type="button" className="mt-6 inline-flex min-h-11 items-center justify-center rounded-full bg-ink px-5 py-2.5 text-sm font-medium text-white transition-transform hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50" onClick={() => onViewDetails?.(active.id)}>
            View details <span className="ml-2" aria-hidden="true">→</span>
          </button>
        </article>
        <div className="workspace-card-tabs" aria-label="Select patient workspace section">
          {sections.map((section, index) => index === activeIndex ? null : (
            <button key={section.id} type="button" className="workspace-card-tab" onClick={() => select(index)} aria-label={`Open ${section.label}`}>
              <span className="font-mono text-[9px] text-muted">{section.number}</span>
              <span className="workspace-card-tab-label">{section.shortLabel}</span>
            </button>
          ))}
        </div>
      </div>
      <p className="mt-2 text-center text-[11px] text-muted sm:text-right">Tap a section tab or swipe to move through the workspace.</p>
    </section>
  );
}

function SafetyBrief({ analysis, findingCount }: { analysis: AnalysisRunResponse | null; findingCount: number }) {
  if (!analysis) return <p className="max-w-xl text-sm leading-6 text-muted">No safety analysis has been run yet. The current medication record is ready for deterministic interaction, ADR and adherence analysis.</p>;
  const risk = analysis.risk_level ? analysis.risk_level[0].toUpperCase() + analysis.risk_level.slice(1) : "Recorded";
  return <div><p className="text-3xl font-semibold tracking-tight">{risk} risk</p><p className="mt-2 text-sm leading-6 text-muted">{findingCount === 0 ? "No interaction or ADR findings were recorded in this analysis." : `${findingCount} safety ${findingCount === 1 ? "finding" : "findings"} recorded in this analysis.`}</p><p className="mt-3 text-[11px] text-muted">Analysis {new Date(analysis.created_at).toLocaleString()}</p></div>;
}

function MedicationBrief({ medications, activeCount }: { medications: MedicationResponse[]; activeCount: number }) {
  const verified = medications.filter((medication) => Boolean(medication.drug_name)).length;
  return <div><p className="text-3xl font-semibold tracking-tight">{activeCount} active</p><p className="mt-2 text-sm leading-6 text-muted">{medications.length} {medications.length === 1 ? "medication" : "medications"} recorded · {verified} verified {verified === 1 ? "identity" : "identities"}.</p></div>;
}

function SymptomBrief({ symptoms, unresolvedCount }: { symptoms: SymptomResponse[]; unresolvedCount: number }) {
  const latest = [...symptoms].sort((a, b) => b.onset_date.localeCompare(a.onset_date))[0];
  return <div><p className="text-3xl font-semibold tracking-tight">{unresolvedCount} unresolved</p><p className="mt-2 text-sm leading-6 text-muted">{symptoms.length} {symptoms.length === 1 ? "symptom" : "symptoms"} recorded{latest ? ` · latest: ${latest.description}` : ""}.</p></div>;
}

function TimelineBrief({ timeline }: { timeline: TimelineEventResponse[] }) {
  const latest = [...timeline].sort((a, b) => b.event_time.localeCompare(a.event_time))[0];
  return <div><p className="text-3xl font-semibold tracking-tight">{timeline.length} recent events</p><p className="mt-2 text-sm leading-6 text-muted">{latest ? latest.event_title : "No timeline activity has been recorded yet."}</p></div>;
}

function getFindingCount(analysis: AnalysisRunResponse): number {
  const result = analysis.deterministic_result;
  if (!result || typeof result !== "object") return 0;
  const interaction = Array.isArray(result.interaction_findings) ? result.interaction_findings.length : 0;
  const adr = Array.isArray(result.adr_findings) ? result.adr_findings.length : 0;
  return interaction + adr;
}
