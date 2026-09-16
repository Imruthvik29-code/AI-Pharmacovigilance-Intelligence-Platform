import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PatientSnapshot } from "@/components/patient/PatientSnapshot";
import { latestClinicalUpdate } from "@/lib/patient/summaries";
import type {
  AnalysisRunResponse,
  MedicationResponse,
  TimelineEventResponse,
} from "@/lib/api/types";

function medication(id: string, status: MedicationResponse["status"]): MedicationResponse {
  return {
    id,
    patient_id: "p1",
    condition_id: null,
    purpose_text: null,
    drug_id: `d-${id}`,
    dose: null,
    times_per_day: null,
    interval_hours: null,
    duration_days: null,
    status,
    start_date: "2026-08-01",
    end_date: null,
    created_at: "",
    updated_at: "",
    drug_name: `Drug ${id}`,
    drug_generic_name: null,
    drug_term_type: null,
    drug_source: null,
  };
}

function run(createdAt: string, risk: AnalysisRunResponse["risk_level"]): AnalysisRunResponse {
  return {
    id: "a1",
    patient_id: "p1",
    analysis_version: "1.0",
    deterministic_result: null,
    safety_score: 74,
    risk_level: risk,
    llm_summary: null,
    llm_reasoning: null,
    llm_recommendations: null,
    confidence_score: null,
    confidence_level: null,
    created_at: createdAt,
  };
}

function event(time: string): TimelineEventResponse {
  return {
    id: `t-${time}`,
    patient_id: "p1",
    event_type: "symptom_reported",
    ref_id: null,
    event_title: "Symptom reported",
    event_description: null,
    event_time: time,
    payload: null,
    created_at: "",
  };
}

describe("latestClinicalUpdate", () => {
  it("takes the timeline event when it is newer than the analysis", () => {
    expect(
      latestClinicalUpdate(run("2026-09-10T10:00:00Z", "moderate"), [
        event("2026-09-01T10:00:00Z"),
        event("2026-09-14T08:30:00Z"),
      ]),
    ).toBe("2026-09-14T08:30:00Z");
  });

  it("takes the analysis when it is newer than every event", () => {
    expect(
      latestClinicalUpdate(run("2026-09-20T10:00:00Z", "moderate"), [event("2026-09-14T08:30:00Z")]),
    ).toBe("2026-09-20T10:00:00Z");
  });

  it("falls back to whichever side exists on its own", () => {
    expect(latestClinicalUpdate(null, [event("2026-09-14T08:30:00Z")])).toBe("2026-09-14T08:30:00Z");
    expect(latestClinicalUpdate(run("2026-09-20T10:00:00Z", "low"), [])).toBe("2026-09-20T10:00:00Z");
  });

  it("has nothing to report when the record is empty", () => {
    expect(latestClinicalUpdate(null, [])).toBeNull();
  });

  it("ignores an unparsable timestamp rather than returning it", () => {
    expect(latestClinicalUpdate(run("not-a-date", "low"), [event("2026-09-14T08:30:00Z")])).toBe(
      "2026-09-14T08:30:00Z",
    );
  });
});

describe("PatientSnapshot", () => {
  it("reports the active count, the deterministic risk level and the last update", () => {
    render(
      <PatientSnapshot
        medications={[medication("m1", "active"), medication("m2", "active"), medication("m3", "completed")]}
        analysis={run("2026-09-12T04:42:00Z", "moderate")}
        timeline={[event("2026-09-01T10:00:00Z")]}
      />,
    );
    expect(screen.getByText("2 of 3 medications")).toBeInTheDocument();
    expect(screen.getByText("Moderate risk")).toBeInTheDocument();
    expect(screen.getByText(/^Updated /)).toBeInTheDocument();
  });

  it("says what is missing instead of inventing a value", () => {
    render(<PatientSnapshot medications={[]} analysis={null} timeline={[]} />);
    expect(screen.getByText("No medications recorded")).toBeInTheDocument();
    expect(screen.getByText("Not analysed yet")).toBeInTheDocument();
    // With neither an analysis nor an event there is no update line at all.
    expect(screen.queryByText(/^Updated /)).not.toBeInTheDocument();
  });

  it("names each risk level the deterministic layer can return", () => {
    for (const level of ["low", "moderate", "high"] as const) {
      const view = render(
        <PatientSnapshot medications={[]} analysis={run("2026-09-12T04:42:00Z", level)} timeline={[]} />,
      );
      expect(
        screen.getByText(`${level[0].toUpperCase()}${level.slice(1)} risk`),
      ).toBeInTheDocument();
      view.unmount();
    }
  });
});
