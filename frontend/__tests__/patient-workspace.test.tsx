import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PatientWorkspace } from "@/components/patient/PatientWorkspace";
import { CATEGORIES } from "@/components/patient/categories";
import type { AnalysisRunResponse } from "@/lib/api/types";

const analysis: AnalysisRunResponse = {
  id: "analysis-1",
  patient_id: "patient-1",
  analysis_version: "1.0",
  deterministic_result: {
    safety_score: 82,
    risk_level: "moderate",
    starting_score: 100,
    total_points_deducted: 18,
    interaction_findings: [
      {
        interaction_rule_id: "i1",
        drug_a_id: "a",
        drug_a_name: "Drug A",
        drug_b_id: "b",
        drug_b_name: "Drug B",
        severity: "severe",
        mechanism: null,
        recommendation: null,
        source: "FDA Label",
      },
    ],
    adr_findings: [
      {
        adr_rule_id: "r1",
        drug_id: "a",
        drug_name: "Drug A",
        reaction_description: "Bruising",
        severity: "moderate",
        frequency_class: null,
        source: "FDA Label",
      },
    ],
    adherence_findings: [],
    penalties: [],
  },
  safety_score: 82,
  risk_level: "moderate",
  llm_summary: null,
  llm_reasoning: null,
  llm_recommendations: null,
  confidence_score: null,
  confidence_level: null,
  created_at: "2026-09-09T10:00:00Z",
};

const emptyData = { analysis: null, medications: [], symptoms: [], timeline: [] };

function renderWorkspace(overrides: Partial<Parameters<typeof PatientWorkspace>[0]> = {}) {
  const props = {
    activeId: "safety" as const,
    onSelect: vi.fn(),
    onOpen: vi.fn(),
    data: emptyData,
    ...overrides,
  };
  render(<PatientWorkspace {...props} />);
  return props;
}

describe("PatientWorkspace", () => {
  it("shows the active category as the foreground card", () => {
    renderWorkspace();
    expect(screen.getByRole("region", { name: "Patient workspace" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Safety" })).toBeInTheDocument();
  });

  it("keeps every other category reachable without scrolling", () => {
    renderWorkspace();
    for (const category of CATEGORIES.filter((item) => item.id !== "safety")) {
      expect(screen.getAllByRole("button", { name: `Show ${category.label}` }).length).toBeGreaterThan(0);
    }
    expect(screen.queryByRole("button", { name: "Show Safety" })).not.toBeInTheDocument();
  });

  it("selects a category when its ribbon is activated", () => {
    const props = renderWorkspace();
    fireEvent.click(screen.getAllByRole("button", { name: "Show Timeline" })[0]);
    expect(props.onSelect).toHaveBeenCalledWith("timeline");
  });

  it("moves between categories with the arrow keys", () => {
    const props = renderWorkspace({ activeId: "medications" });
    const region = screen.getByRole("region", { name: "Patient workspace" });
    const stage = region.querySelector(".px-stage") as HTMLElement;

    fireEvent.keyDown(stage, { key: "ArrowRight" });
    expect(props.onSelect).toHaveBeenCalledWith("symptoms");

    fireEvent.keyDown(stage, { key: "ArrowLeft" });
    expect(props.onSelect).toHaveBeenCalledWith("safety");
  });

  it("advances on a horizontal swipe", () => {
    const props = renderWorkspace();
    const region = screen.getByRole("region", { name: "Patient workspace" });
    const stage = region.querySelector(".px-stage") as HTMLElement;
    fireEvent(stage, new MouseEvent("pointerdown", { bubbles: true, clientX: 300 }));
    fireEvent(stage, new MouseEvent("pointerup", { bubbles: true, clientX: 180 }));
    expect(props.onSelect).toHaveBeenCalledWith("medications");
  });

  it("offers Run analysis while Safety has no run, and View details once it does", () => {
    const onRunAnalysis = vi.fn();
    const props = renderWorkspace({ onRunAnalysis });
    fireEvent.click(screen.getByRole("button", { name: /Run analysis/ }));
    expect(onRunAnalysis).toHaveBeenCalled();
    expect(props.onOpen).not.toHaveBeenCalled();
  });

  it("opens the detail view from the card CTA", () => {
    const props = renderWorkspace({ data: { ...emptyData, analysis }, onRunAnalysis: vi.fn() });
    fireEvent.click(screen.getByRole("button", { name: "Open Safety details" }));
    expect(props.onOpen).toHaveBeenCalledWith("safety");
  });

  it("reports the recorded severity split rather than a bare count", () => {
    renderWorkspace({ data: { ...emptyData, analysis } });
    expect(screen.getByText("2 safety findings")).toBeInTheDocument();
    expect(screen.getByText("1 severe · 1 moderate")).toBeInTheDocument();
    expect(screen.getByText("Safety score 82 of 100 · moderate risk")).toBeInTheDocument();
  });

  it("does not invent a score or findings when the payload has none", () => {
    const bare: AnalysisRunResponse = {
      ...analysis,
      deterministic_result: null,
      safety_score: null,
      risk_level: null,
    };
    renderWorkspace({ data: { ...emptyData, analysis: bare } });
    expect(screen.queryByText(/Safety score/)).not.toBeInTheDocument();
    expect(screen.queryByText(/safety findings/)).not.toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("announces the selected category to assistive technology", () => {
    renderWorkspace({ activeId: "symptoms" });
    expect(screen.getByRole("status")).toHaveTextContent("Symptoms selected");
  });
});
