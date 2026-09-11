import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PatientWorkspaceCards } from "@/components/PatientWorkspaceCards";

const analysis = { id: "analysis-1", patient_id: "patient-1", analysis_version: "1.0", deterministic_result: { safety_score: 82, risk_level: "moderate" as const, starting_score: 100, total_points_deducted: 18, interaction_findings: [{ interaction_rule_id: "i1" }], adr_findings: [], adherence_findings: [], penalties: [] }, safety_score: 82, risk_level: "moderate" as const, llm_summary: null, llm_reasoning: null, llm_recommendations: null, confidence_score: null, confidence_level: null, created_at: "2026-09-09T10:00:00Z" };

describe("PatientWorkspaceCards", () => {
  it("starts on Safety with all four integrated section controls", () => {
    render(<PatientWorkspaceCards analysis={analysis} medications={[]} symptoms={[]} timeline={[]} onViewDetails={vi.fn()} onRunAnalysis={vi.fn()} analysisRunning={false} />);
    expect(screen.getByRole("region", { name: "Patient workspace" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Safety" })).toBeInTheDocument();
    expect(screen.getByText("Moderate risk")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Safety" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: "Open Medications" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Symptoms" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Timeline" })).toBeInTheDocument();
  });

  it("selects a section by tap and opens its matching details", () => {
    vi.useFakeTimers();
    try {
      const onViewDetails = vi.fn();
      render(<PatientWorkspaceCards analysis={analysis} medications={[]} symptoms={[]} timeline={[]} onViewDetails={onViewDetails} onRunAnalysis={vi.fn()} analysisRunning={false} />);
      fireEvent.click(screen.getByRole("button", { name: "Open Symptoms" }));
      act(() => vi.advanceTimersByTime(300));
      expect(screen.getByRole("heading", { name: "Symptoms" })).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "View details" }));
      expect(onViewDetails).toHaveBeenCalledWith("symptoms");
    } finally { vi.useRealTimers(); }
  });

  it("advances left and returns right using directional card swipes", () => {
    vi.useFakeTimers();
    try {
      render(<PatientWorkspaceCards analysis={null} medications={[]} symptoms={[]} timeline={[]} onViewDetails={vi.fn()} onRunAnalysis={vi.fn()} analysisRunning={false} />);
      const stage = screen.getByRole("region", { name: "Patient workspace" }).querySelector(".workspace-card-stage");
      fireEvent(stage!, new MouseEvent("pointerdown", { bubbles: true, clientX: 300 }));
      fireEvent(stage!, new MouseEvent("pointerup", { bubbles: true, clientX: 180 }));
      act(() => vi.advanceTimersByTime(300));
      expect(screen.getByRole("heading", { name: "Medications" })).toBeInTheDocument();
      fireEvent(stage!, new MouseEvent("pointerdown", { bubbles: true, clientX: 180 }));
      fireEvent(stage!, new MouseEvent("pointerup", { bubbles: true, clientX: 300 }));
      act(() => vi.advanceTimersByTime(300));
      expect(screen.getByRole("heading", { name: "Safety" })).toBeInTheDocument();
    } finally { vi.useRealTimers(); }
  });

  it("moves between adjacent sections with arrow keys", () => {
    render(<PatientWorkspaceCards analysis={analysis} medications={[]} symptoms={[]} timeline={[]} />);
    const carousel = screen.getByRole("group", { name: /Safety, section 1 of 4/ });
    fireEvent.keyDown(carousel, { key: "ArrowRight" });
    expect(screen.getByRole("heading", { name: "Medications" })).toBeInTheDocument();
    fireEvent.keyDown(carousel, { key: "ArrowLeft" });
    expect(screen.getByRole("heading", { name: "Safety" })).toBeInTheDocument();
  });

  it("offers the deterministic analysis action only in the unanalysed Safety state", () => {
    const onRunAnalysis = vi.fn();
    render(<PatientWorkspaceCards analysis={null} medications={[]} symptoms={[]} timeline={[]} onViewDetails={vi.fn()} onRunAnalysis={onRunAnalysis} analysisRunning={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));
    expect(onRunAnalysis).toHaveBeenCalledOnce();
  });
});
