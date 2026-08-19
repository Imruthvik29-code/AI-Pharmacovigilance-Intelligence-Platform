import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalysisHero } from "@/components/AnalysisHero";
import type { AnalysisRunResponse } from "@/lib/api/types";

const sampleRun: AnalysisRunResponse = {
  id: "run-1",
  patient_id: "patient-1",
  analysis_version: "v1.0",
  safety_score: 42,
  risk_level: "moderate",
  deterministic_result: {
    safety_score: 42,
    risk_level: "moderate",
    starting_score: 100,
    total_points_deducted: 58,
    interaction_findings: [],
    adr_findings: [],
    adherence_findings: [],
    penalties: [],
  },
  llm_summary: null,
  llm_reasoning: null,
  llm_recommendations: null,
  confidence_score: null,
  confidence_level: null,
  created_at: "2026-08-19T12:00:00Z",
};

describe("AnalysisHero", () => {
  it("surfaces an analysis-history error instead of pretending none exists", () => {
    render(
      <AnalysisHero
        run={null}
        historyError="Request failed (502)."
        historyLoaded
        running={false}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load analysis history");
    expect(screen.queryByText("No analysis yet")).not.toBeInTheDocument();
  });

  it("shows the empty state only after history loaded successfully", () => {
    render(
      <AnalysisHero run={null} historyError={null} historyLoaded running={false} />,
    );
    expect(screen.getByText("No analysis yet")).toBeInTheDocument();
  });

  it("keeps a previous report visible while a new analysis is running", () => {
    render(
      <AnalysisHero run={sampleRun} historyError={null} historyLoaded running />,
    );
    expect(screen.getByText(/Running analysis/)).toBeInTheDocument();
    expect(screen.getByLabelText("Safety score")).toHaveTextContent("42");
    expect(screen.queryByText("No analysis yet")).not.toBeInTheDocument();
  });

  it("still renders a known run when history refresh later fails", () => {
    render(
      <AnalysisHero
        run={sampleRun}
        historyError="Request failed (502)."
        historyLoaded
        running={false}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load analysis history");
    expect(screen.getByLabelText("Safety score")).toHaveTextContent("42");
  });
});
