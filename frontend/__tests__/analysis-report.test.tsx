import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalysisReport } from "@/components/AnalysisReport";
import type { AnalysisRunResponse } from "@/lib/api/types";

function run(overrides: Partial<AnalysisRunResponse> = {}): AnalysisRunResponse {
  return {
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
      interaction_findings: [
        {
          interaction_rule_id: "int-1",
          drug_a_id: "a",
          drug_a_name: "Drug A",
          drug_b_id: "b",
          drug_b_name: "Drug B",
          severity: "moderate",
          mechanism: "Example mechanism from backend.",
          recommendation: "Example recommendation from backend.",
          source: "Example Source",
        },
      ],
      adr_findings: [
        {
          adr_rule_id: "adr-1",
          drug_id: "a",
          drug_name: "Drug A",
          reaction_description: "Example reaction",
          severity: "mild",
          frequency_class: "common",
          source: "Example Source",
        },
      ],
      adherence_findings: [],
      penalties: [
        {
          category: "drug_interaction",
          description: "Drug A + Drug B interaction (moderate)",
          severity: "moderate",
          points: 15,
        },
      ],
    },
    llm_summary: null,
    llm_reasoning: null,
    llm_recommendations: null,
    confidence_score: null,
    confidence_level: null,
    created_at: "2026-08-19T12:00:00Z",
    ...overrides,
  };
}

describe("AnalysisReport", () => {
  it("renders backend-provided score and risk without substituting defaults", () => {
    render(<AnalysisReport run={run({ safety_score: 42, risk_level: "moderate" })} />);
    expect(screen.getByLabelText("Safety score")).toHaveTextContent("42");
    expect(screen.getByLabelText("Safety score")).toHaveTextContent("moderate");
    expect(screen.queryByText("25")).not.toBeInTheDocument();
  });

  it("renders a different backend score/risk when the payload changes", () => {
    render(<AnalysisReport run={run({ safety_score: 25, risk_level: "high" })} />);
    expect(screen.getByLabelText("Safety score")).toHaveTextContent("25");
    expect(screen.getByLabelText("Safety score")).toHaveTextContent("high");
  });

  it("renders interaction and ADR findings from the backend payload", () => {
    render(<AnalysisReport run={run()} />);
    expect(screen.getByText("Drug A + Drug B")).toBeInTheDocument();
    expect(screen.getByText("Example mechanism from backend.")).toBeInTheDocument();
    expect(screen.getByText("Example recommendation from backend.")).toBeInTheDocument();
    expect(screen.getByText(/Example reaction/)).toBeInTheDocument();
    expect(screen.getByText("Drug A + Drug B interaction (moderate)")).toBeInTheDocument();
    expect(screen.getAllByText(/Drug A/).length).toBeGreaterThan(0);
  });

  it("shows an unavailable explanation when llm_summary is null", () => {
    render(<AnalysisReport run={run({ llm_summary: null })} />);
    expect(screen.getByText("AI explanation unavailable for this analysis.")).toBeInTheDocument();
    expect(screen.queryByText(/discuss with the prescriber/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/completely safe/i)).not.toBeInTheDocument();
  });

  it("renders llm_summary when the backend supplies one and still does not invent confidence", () => {
    render(
      <AnalysisReport
        run={run({
          llm_summary: "Backend-provided explanation only.",
          llm_reasoning: null,
          llm_recommendations: null,
          confidence_score: null,
          confidence_level: null,
        })}
      />,
    );
    expect(screen.getByText("Backend-provided explanation only.")).toBeInTheDocument();
    expect(screen.queryByText(/Confidence/)).not.toBeInTheDocument();
  });

  it("does not invent findings when arrays are empty", () => {
    render(
      <AnalysisReport
        run={run({
          deterministic_result: {
            safety_score: 100,
            risk_level: "low",
            starting_score: 100,
            total_points_deducted: 0,
            interaction_findings: [],
            adr_findings: [],
            adherence_findings: [],
            penalties: [],
          },
          safety_score: 100,
          risk_level: "low",
        })}
      />,
    );
    expect(screen.getByText("No interaction findings in this analysis.")).toBeInTheDocument();
    expect(screen.getByText("No ADR findings in this analysis.")).toBeInTheDocument();
    expect(screen.getByText("No penalties were recorded for this run.")).toBeInTheDocument();
  });
});
