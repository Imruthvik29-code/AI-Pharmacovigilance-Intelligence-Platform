import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PatientWorkspaceCards } from "@/components/PatientWorkspaceCards";

const analysis = {
  id: "analysis-1", patient_id: "patient-1", analysis_version: "1.0",
  deterministic_result: { safety_score: 82, risk_level: "moderate" as const, starting_score: 100, total_points_deducted: 18, interaction_findings: [{ interaction_rule_id: "i1" }], adr_findings: [], adherence_findings: [], penalties: [] },
  safety_score: 82, risk_level: "moderate" as const, llm_summary: null, llm_reasoning: null, llm_recommendations: null, confidence_score: null, confidence_level: null, created_at: "2026-09-09T10:00:00Z",
};

describe("PatientWorkspaceCards", () => {
  it("shows a brief for the active section and compact tabs for the rest", () => {
    render(<PatientWorkspaceCards analysis={analysis} medications={[]} symptoms={[]} timeline={[]} />);
    expect(screen.getByRole("region", { name: "Patient workspace" })).toBeInTheDocument();
    expect(screen.getByText("Moderate risk")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Medications" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Symptoms" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Timeline" })).toBeInTheDocument();
    expect(screen.getByText("1 safety finding recorded in this analysis.")).toBeInTheDocument();
  });

  it("selects a tab and exposes its details action", () => {
    const onViewDetails = vi.fn();
    render(<PatientWorkspaceCards analysis={analysis} medications={[]} symptoms={[]} timeline={[]} onViewDetails={onViewDetails} />);
    fireEvent.click(screen.getByRole("button", { name: "Open Medications" }));
    expect(screen.getByRole("heading", { name: "Medications" })).toBeInTheDocument();
    expect(screen.getByText("0 active")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /View details/ }));
    expect(onViewDetails).toHaveBeenCalledWith("medications");
  });

  it("advances with a horizontal swipe", () => {
    render(<PatientWorkspaceCards analysis={null} medications={[]} symptoms={[]} timeline={[]} />);
    const workspace = screen.getByRole("region", { name: "Patient workspace" });
    fireEvent.pointerDown(workspace, { clientX: 300 });
    fireEvent.pointerUp(workspace, { clientX: 180 });
    expect(screen.getByText("2 / 4")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Medications" })).toBeInTheDocument();
  });
});
