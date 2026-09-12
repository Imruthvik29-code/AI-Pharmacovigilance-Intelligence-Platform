import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { PatientCardStack } from "@/components/patient/PatientCardStack";
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

/**
 * jsdom reports every element as zero-sized. Give the stage a real width so
 * the deck can compute how far a card has to travel.
 */
const STAGE_WIDTH = 360;

beforeAll(() => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    width: STAGE_WIDTH,
    height: 360,
    top: 0,
    left: 0,
    right: STAGE_WIDTH,
    bottom: 360,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
});

function renderStack(overrides: Partial<Parameters<typeof PatientCardStack>[0]> = {}) {
  const props = {
    activeId: "safety" as const,
    onSelect: vi.fn(),
    onOpen: vi.fn(),
    data: emptyData,
    ...overrides,
  };
  const view = render(<PatientCardStack {...props} />);
  const stage = view.container.querySelector(".pv-stage") as HTMLElement;
  return { ...props, stage, view };
}

function at(type: string, clientX: number, clientY: number, timeStamp: number) {
  const event = new MouseEvent(type, { bubbles: true, clientX, clientY });
  Object.defineProperty(event, "timeStamp", { value: timeStamp });
  return event;
}

/** A horizontal drag of dx px over ms, as a pointer device would deliver it. */
function swipe(stage: HTMLElement, dx: number, ms = 120) {
  const from = 240;
  fireEvent(stage, at("pointerdown", from, 300, 1000));
  fireEvent(stage, at("pointermove", from + dx / 2, 302, 1000 + ms / 2));
  fireEvent(stage, at("pointermove", from + dx, 304, 1000 + ms));
  fireEvent(stage, at("pointerup", from + dx, 304, 1000 + ms));
}

function cardFor(view: ReturnType<typeof render>, label: string): HTMLElement {
  const heading = view.getByRole("heading", { name: label, hidden: true });
  return heading.closest(".pv-card") as HTMLElement;
}

function translateX(card: HTMLElement): number {
  const match = /translate3d\((-?[\d.]+)px/.exec(card.style.transform);
  return match ? Number(match[1]) : Number.NaN;
}

describe("PatientCardStack", () => {
  it("puts the active category in the foreground card", () => {
    const { view } = renderStack();
    expect(screen.getByRole("region", { name: "Patient workspace" })).toBeInTheDocument();
    expect(cardFor(view, "Safety")).not.toHaveAttribute("aria-hidden");
    expect(cardFor(view, "Medications")).toHaveAttribute("aria-hidden", "true");
  });

  it("keeps every other category reachable as a ribbon", () => {
    renderStack();
    for (const category of CATEGORIES.filter((item) => item.id !== "safety")) {
      expect(screen.getByRole("button", { name: `Show ${category.label}` })).toBeInTheDocument();
    }
  });

  it("selects a category when its ribbon is activated", () => {
    const props = renderStack();
    fireEvent.click(screen.getByRole("button", { name: "Show Timeline" }));
    expect(props.onSelect).toHaveBeenCalledWith("timeline");
  });

  // --------------------------------------------------------------- direction
  it("parks the previous card left and the next card right of the foreground", () => {
    const { view } = renderStack({ activeId: "medications" });
    expect(translateX(cardFor(view, "Safety"))).toBe(-STAGE_WIDTH);
    expect(translateX(cardFor(view, "Medications"))).toBe(0);
    expect(translateX(cardFor(view, "Symptoms"))).toBe(STAGE_WIDTH);
  });

  it("swipes LEFT to advance: current card travels left, next arrives from the right", () => {
    const { stage, onSelect } = renderStack({ activeId: "medications" });
    swipe(stage, -140);
    expect(onSelect).toHaveBeenCalledWith("symptoms");
  });

  it("swipes RIGHT to go back: current card travels right, previous arrives from the left", () => {
    const { stage, onSelect } = renderStack({ activeId: "medications" });
    swipe(stage, 140);
    expect(onSelect).toHaveBeenCalledWith("safety");
  });

  it("moves the cards themselves during a drag rather than swapping content", () => {
    const { stage, view } = renderStack({ activeId: "medications" });
    fireEvent(stage, at("pointerdown", 240, 300, 1000));
    fireEvent(stage, at("pointermove", 170, 301, 1060));

    // The foreground card has physically followed the pointer to the left.
    expect(translateX(cardFor(view, "Medications"))).toBe(-70);
    // The incoming card has travelled with it and is still to the right.
    expect(translateX(cardFor(view, "Symptoms"))).toBe(STAGE_WIDTH - 70);

    fireEvent(stage, at("pointercancel", 170, 301, 1080));
    expect(translateX(cardFor(view, "Medications"))).toBe(0);
  });

  // -------------------------------------------------------------- boundaries
  it("resists past the first card instead of tearing free", () => {
    const { stage, onSelect, view } = renderStack({ activeId: "safety" });
    fireEvent(stage, at("pointerdown", 240, 300, 1000));
    fireEvent(stage, at("pointermove", 400, 300, 1060));
    expect(translateX(cardFor(view, "Safety"))).toBeCloseTo(160 * 0.32, 1);
    fireEvent(stage, at("pointerup", 400, 300, 1060));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("does not move past the last card", () => {
    const { stage, onSelect } = renderStack({ activeId: "timeline" });
    fireEvent(stage, at("pointerdown", 240, 300, 1000));
    fireEvent(stage, at("pointermove", 80, 300, 1060));
    fireEvent(stage, at("pointerup", 80, 300, 1060));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("ignores a drag too short and too slow to be intentional", () => {
    const { stage, onSelect } = renderStack({ activeId: "medications" });
    fireEvent(stage, at("pointerdown", 240, 300, 1000));
    fireEvent(stage, at("pointermove", 228, 300, 1300));
    fireEvent(stage, at("pointerup", 228, 300, 1600));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("commits a short but fast flick", () => {
    const { stage, onSelect } = renderStack({ activeId: "medications" });
    fireEvent(stage, at("pointerdown", 240, 300, 1000));
    fireEvent(stage, at("pointermove", 210, 300, 1020));
    fireEvent(stage, at("pointerup", 210, 300, 1030));
    expect(onSelect).toHaveBeenCalledWith("symptoms");
  });

  it("abandons the gesture when the intent is vertical scrolling", () => {
    const { stage, onSelect } = renderStack({ activeId: "medications" });
    fireEvent(stage, at("pointerdown", 240, 300, 1000));
    fireEvent(stage, at("pointermove", 236, 380, 1060));
    fireEvent(stage, at("pointerup", 120, 380, 1120));
    expect(onSelect).not.toHaveBeenCalled();
  });

  // ---------------------------------------------------------------- keyboard
  it("moves along the deck with the arrow keys", () => {
    const { stage, onSelect } = renderStack({ activeId: "medications" });
    fireEvent.keyDown(stage, { key: "ArrowRight" });
    expect(onSelect).toHaveBeenCalledWith("symptoms");
    fireEvent.keyDown(stage, { key: "ArrowLeft" });
    expect(onSelect).toHaveBeenCalledWith("safety");
  });

  it("announces the active card to assistive technology", () => {
    renderStack({ activeId: "symptoms" });
    expect(screen.getByRole("status")).toHaveTextContent("Symptoms selected, 3 of 4");
  });

  // -------------------------------------------------------------------- data
  it("offers Run analysis until Safety has a run", () => {
    const onRunAnalysis = vi.fn();
    renderStack({ onRunAnalysis });
    fireEvent.click(screen.getByRole("button", { name: /Run analysis/ }));
    expect(onRunAnalysis).toHaveBeenCalled();
  });

  it("opens the detail screen from the card CTA", () => {
    const props = renderStack({ data: { ...emptyData, analysis } });
    fireEvent.click(screen.getByRole("button", { name: "Open Safety details" }));
    expect(props.onOpen).toHaveBeenCalledWith("safety");
  });

  it("reports the recorded severity split rather than a bare count", () => {
    renderStack({ data: { ...emptyData, analysis } });
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
    renderStack({ data: { ...emptyData, analysis: bare } });
    expect(screen.queryByText(/Safety score/)).not.toBeInTheDocument();
    expect(screen.queryByText(/safety findings/)).not.toBeInTheDocument();
  });
});
