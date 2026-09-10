"use client";

import { PatientWorkspaceCards, type WorkspaceCardId } from "@/components/PatientWorkspaceCards";
import type { AnalysisRunResponse, MedicationResponse, SymptomResponse, TimelineEventResponse } from "@/lib/api/types";

type Props = {
  analysis: AnalysisRunResponse | null;
  medications: MedicationResponse[];
  symptoms: SymptomResponse[];
  timeline: TimelineEventResponse[];
  onViewDetails: (id: WorkspaceCardId) => void;
  onRunAnalysis: () => void;
  analysisRunning: boolean;
};

const productSections: Array<{ id: WorkspaceCardId; label: string }> = [
  { id: "safety", label: "Safety" },
  { id: "medications", label: "Medications" },
  { id: "symptoms", label: "Symptoms" },
  { id: "timeline", label: "Timeline" },
];

export function PatientOverviewSheet({ analysis, medications, symptoms, timeline, onViewDetails, onRunAnalysis, analysisRunning }: Props) {
  return (
    <section className="patient-overview-sheet" aria-label="Patient overview">
      <nav className="patient-overview-nav" aria-label="Patient sections">
        <button type="button" className="patient-overview-nav-item is-active" aria-current="page">Overview</button>
        {productSections.map((section) => (
          <button key={section.id} type="button" className="patient-overview-nav-item" onClick={() => onViewDetails(section.id)}>
            {section.label}
          </button>
        ))}
      </nav>
      <PatientWorkspaceCards
        analysis={analysis}
        medications={medications}
        symptoms={symptoms}
        timeline={timeline}
        onViewDetails={onViewDetails}
        onRunAnalysis={onRunAnalysis}
        analysisRunning={analysisRunning}
      />
    </section>
  );
}
