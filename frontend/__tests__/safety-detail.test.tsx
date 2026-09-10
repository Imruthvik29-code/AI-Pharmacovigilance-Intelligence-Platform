import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SafetyDetail } from "@/components/SafetyDetail";
import type { AnalysisRunResponse } from "@/lib/api/types";

const run: AnalysisRunResponse = {
  id: "run-1", patient_id: "patient-1", analysis_version: "1.0", safety_score: 55, risk_level: "high",
  llm_summary: "This must not appear", llm_reasoning: null, llm_recommendations: null, confidence_score: null, confidence_level: null,
  created_at: "2026-09-10T08:00:00Z",
  deterministic_result: {
    safety_score: 55, risk_level: "high", starting_score: 100, total_points_deducted: 45, adherence_findings: [], penalties: [],
    interaction_findings: [{ interaction_rule_id: "interaction-1", drug_a_id: "a", drug_a_name: "Warfarin", drug_b_id: "b", drug_b_name: "Aspirin", severity: "severe", mechanism: "Increased bleeding risk", recommendation: "Review concurrent use", source: "Rule source" }],
    adr_findings: [{ adr_rule_id: "adr-1", drug_id: "a", drug_name: "Warfarin", reaction_description: "Bleeding", severity: "moderate", frequency_class: "common", source: "ADR source" }],
  },
};

describe("SafetyDetail", () => {
  it("renders deterministic status and key-finding rows without inventing completeness", () => {
    render(<SafetyDetail run={run} historyError={null} historyLoaded running={false} onRunAnalysis={vi.fn()} />);
    expect(screen.getByText("2 deterministic findings")).toBeInTheDocument();
    expect(screen.getByText("1 severe · 1 moderate")).toBeInTheDocument();
    expect(screen.getByText("Warfarin + Aspirin")).toBeInTheDocument();
    expect(screen.getByText("Increased bleeding risk")).toBeInTheDocument();
    expect(screen.getByText("Bleeding")).toBeInTheDocument();
    expect(screen.getByText("Latest analysis")).toBeInTheDocument();
    expect(screen.queryByText(/completeness/i)).not.toBeInTheDocument();
    expect(screen.queryByText("This must not appear")).not.toBeInTheDocument();
  });

  it("uses the supplied existing analysis operation for the bottom CTA", () => {
    const onRunAnalysis = vi.fn();
    render(<SafetyDetail run={run} historyError={null} historyLoaded running={false} onRunAnalysis={onRunAnalysis} />);
    fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));
    expect(onRunAnalysis).toHaveBeenCalledOnce();
  });
});
