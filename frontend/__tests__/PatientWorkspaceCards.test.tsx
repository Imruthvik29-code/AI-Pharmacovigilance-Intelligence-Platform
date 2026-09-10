import { act, fireEvent, render, screen } from "@testing-library/react";
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
    vi.useFakeTimers();
    try {
      const onViewDetails = vi.fn();
      render(<PatientWorkspaceCards analysis={analysis} medications={[]} symptoms={[]} timeline={[]} onViewDetails={onViewDetails} />);
      fireEvent.click(screen.getByRole("button", { name: "Open Medications" }));
      act(() => vi.advanceTimersByTime(300));
      expect(screen.getByRole("heading", { name: "Medications" })).toBeInTheDocument();
      expect(screen.getByText("0 active")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /View details/ }));
      expect(onViewDetails).toHaveBeenCalledWith("medications");
    } finally {
      vi.useRealTimers();
    }
  });

  it("advances with a horizontal swipe and commits the next card after its exit animation", () => {
    vi.useFakeTimers();
    try {
      render(<PatientWorkspaceCards analysis={null} medications={[]} symptoms={[]} timeline={[]} />);
      const workspace = screen.getByRole("region", { name: "Patient workspace" });
      const stage = workspace.querySelector(".workspace-card-stage");
      expect(stage).not.toBeNull();
      fireEvent(stage!, new MouseEvent("pointerdown", { bubbles: true, clientX: 300 }));
      fireEvent(stage!, new MouseEvent("pointerup", { bubbles: true, clientX: 180 }));
      expect(screen.getByText("1 / 4")).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(300));
      expect(screen.getByText("2 / 4")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Medications" })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("moves backward when swiping right", () => {
    vi.useFakeTimers();
    try {
      render(<PatientWorkspaceCards analysis={null} medications={[]} symptoms={[]} timeline={[]} />);
      const workspace = screen.getByRole("region", { name: "Patient workspace" });
      fireEvent.click(screen.getByRole("button", { name: "Open Symptoms" }));
      act(() => vi.advanceTimersByTime(300));
      expect(screen.getByRole("heading", { name: "Symptoms" })).toBeInTheDocument();

      const stage = workspace.querySelector(".workspace-card-stage");
      expect(stage).not.toBeNull();
      fireEvent(stage!, new MouseEvent("pointerdown", { bubbles: true, clientX: 180 }));
      fireEvent(stage!, new MouseEvent("pointerup", { bubbles: true, clientX: 300 }));
      act(() => vi.advanceTimersByTime(300));
      expect(screen.getByText("2 / 4")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Medications" })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
