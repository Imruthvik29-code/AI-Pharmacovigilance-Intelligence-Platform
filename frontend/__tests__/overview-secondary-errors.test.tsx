import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PatientPageRoute from "@/app/patients/[patientId]/page";
import { ApiError } from "@/lib/api/errors";
import { getPatient } from "@/lib/api/patients";
import { listMedications } from "@/lib/api/medications";
import { listSymptoms } from "@/lib/api/symptoms";
import { listTimeline } from "@/lib/api/timeline";
import { listAnalysisRuns } from "@/lib/api/analysis";
import { briefRows, briefSummary, type WorkspaceData } from "@/components/patient/categoryBrief";
import type { AnalysisRunResponse, PatientResponse } from "@/lib/api/types";

vi.mock("next/navigation", () => ({
  useParams: () => ({ patientId: "patient-123" }),
  usePathname: () => "/patients/patient-123",
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("@/components/AuthGate", () => ({
  AuthGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("@/lib/api/patients", () => ({ getPatient: vi.fn() }));
vi.mock("@/lib/api/medications", () => ({ listMedications: vi.fn() }));
vi.mock("@/lib/api/symptoms", () => ({ listSymptoms: vi.fn() }));
vi.mock("@/lib/api/timeline", () => ({ listTimeline: vi.fn() }));
vi.mock("@/lib/api/analysis", () => ({ listAnalysisRuns: vi.fn(), runAnalysis: vi.fn() }));

const patient: PatientResponse = {
  id: "patient-123", user_id: "user-123", name: "Asha Rao", age: 42,
  sex: "female", weight_kg: 64, renal_flag: false, hepatic_flag: false,
  timezone: null, breakfast_time: null, lunch_time: null, dinner_time: null,
  created_at: "2026-09-08T10:00:00Z", updated_at: "2026-09-08T10:00:00Z",
};
const states = [
  { id: "safety", label: "Safety", request: listAnalysisRuns,
    errorKey: "analysisHistoryError", unavailable: "Analysis history unavailable",
    empty: "No analysis has been run for this record yet" },
  { id: "symptoms", label: "Symptoms", request: listSymptoms,
    errorKey: "symptomsError", unavailable: "Symptom data unavailable",
    empty: "No symptoms reported" },
  { id: "timeline", label: "Timeline", request: listTimeline,
    errorKey: "timelineError", unavailable: "Timeline data unavailable",
    empty: "No events recorded yet" },
] as const;

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getPatient).mockResolvedValue(patient);
  vi.mocked(listMedications).mockResolvedValue([]);
  vi.mocked(listSymptoms).mockResolvedValue([]);
  vi.mocked(listTimeline).mockResolvedValue([]);
  vi.mocked(listAnalysisRuns).mockResolvedValue([]);
});

async function cardFor(label: string) {
  await screen.findByRole("heading", { name: "Asha Rao" });
  if (label !== "Safety") fireEvent.click(screen.getByRole("button", { name: `Show ${label}` }));
  return within(screen.getByRole("heading", { name: label }).closest("article")!);
}

describe("Overview secondary request failures", () => {
  it.each(states)("does not turn a failed $id request into an empty record", async (state) => {
    vi.mocked(state.request).mockRejectedValue(new ApiError(503, "Temporarily unavailable."));
    render(<PatientPageRoute />);
    const card = await cardFor(state.label);
    expect(await card.findByText(state.unavailable)).toBeInTheDocument();
    expect(card.queryByText(state.empty)).not.toBeInTheDocument();
    expect(card.getByRole("button", { name: `Open ${state.label} details` })).toBeInTheDocument();
    if (state.id === "safety") {
      expect(screen.queryByText("Not analysed yet")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Run analysis" })).not.toBeInTheDocument();
    }
    const data = { analysis: null, medications: [], symptoms: [], timeline: [],
      [state.errorKey]: "Temporarily unavailable." };
    expect(briefSummary(state.id, data)).toBe(state.unavailable);
  });

  it.each(states)("retains the real $id empty state after a successful empty response", async (state) => {
    render(<PatientPageRoute />);
    const card = await cardFor(state.label);
    expect(await card.findByText(state.empty)).toBeInTheDocument();
    expect(card.queryByText(state.unavailable)).not.toBeInTheDocument();
    if (state.id === "safety") {
      expect(screen.getByRole("button", { name: "Run analysis" })).toBeInTheDocument();
    }
  });

  it("preserves a known stored assessment when a later history request fails", () => {
    const analysis: AnalysisRunResponse = {
      id: "known-run", patient_id: patient.id, analysis_version: "v1.0",
      deterministic_result: null, safety_score: 82, risk_level: "moderate",
      llm_summary: null, llm_reasoning: null, llm_recommendations: null,
      confidence_score: null, confidence_level: null, created_at: "2026-09-08T10:00:00Z",
    };
    const data: WorkspaceData = { analysis, medications: [], symptoms: [], timeline: [],
      analysisHistoryError: "Temporarily unavailable." };
    expect(briefRows("safety", data).map((row) => row.text))
      .toContain("Safety score 82 of 100 · moderate risk");
    expect(briefSummary("safety", data)).toBe("Analysis recorded");
  });
});
