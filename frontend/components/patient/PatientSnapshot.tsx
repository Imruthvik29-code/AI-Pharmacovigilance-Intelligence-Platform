import type { ComponentType } from "react";
import { CalendarIcon, CapsuleIcon, ShieldIcon } from "@/components/icons/Icons";
import {
  activeMedicationCount,
  formatShortDateTime,
  latestClinicalUpdate,
} from "@/lib/patient/summaries";
import type {
  AnalysisRunResponse,
  MedicationResponse,
  TimelineEventResponse,
} from "@/lib/api/types";

type Fact = { key: string; Icon: ComponentType<{ className?: string }>; text: string };

/**
 * The compact record snapshot under the patient's name: what is on file, the
 * deterministic risk classification, and when the record last changed.
 *
 * Every line is read from the payload the workspace has already loaded — no
 * extra request, no derived clinical judgement, and nothing invented. A line
 * whose value is absent is omitted rather than filled in with a placeholder,
 * so an empty record simply shows fewer lines.
 */
export function PatientSnapshot({
  medications,
  medicationsError,
  analysis,
  analysisHistoryError,
  timeline,
}: {
  medications: MedicationResponse[];
  medicationsError?: string | null;
  analysis: AnalysisRunResponse | null;
  analysisHistoryError?: string | null;
  timeline: TimelineEventResponse[];
}) {
  const facts: Fact[] = [];

  facts.push({
    key: "medications",
    Icon: CapsuleIcon,
    text: medicationsError
      ? "Medication data unavailable"
      : medications.length === 0
        ? "No medications recorded"
        : `${activeMedicationCount(medications)} of ${medications.length} medications`,
  });

  // The deterministic risk level, never the LLM's confidence.
  facts.push({
    key: "risk",
    Icon: ShieldIcon,
    text: analysis?.risk_level
      ? `${analysis.risk_level[0].toUpperCase()}${analysis.risk_level.slice(1)} risk`
      : analysisHistoryError
        ? "Analysis history unavailable"
        : "Not analysed yet",
  });

  const updated = latestClinicalUpdate(analysis, timeline);
  if (updated) {
    facts.push({
      key: "updated",
      Icon: CalendarIcon,
      text: `Updated ${formatShortDateTime(updated)}`,
    });
  }

  return (
    <ul className="pv-snap">
      {facts.map((fact) => (
        <li key={fact.key} className="pv-snap-item">
          <fact.Icon className="pv-snap-icon" />
          <span className="pv-snap-text">{fact.text}</span>
        </li>
      ))}
    </ul>
  );
}
