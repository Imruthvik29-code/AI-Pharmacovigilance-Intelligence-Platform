import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PatientPageRoute from "@/app/patients/[patientId]/page";
import { ApiError } from "@/lib/api/errors";
import { getPatient } from "@/lib/api/patients";
import { listMedications } from "@/lib/api/medications";
import { listSymptoms } from "@/lib/api/symptoms";
import { listTimeline } from "@/lib/api/timeline";
import { listAnalysisRuns, runAnalysis } from "@/lib/api/analysis";
import type { AnalysisRunResponse, MedicationResponse } from "@/lib/api/types";

const nav = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  search: new URLSearchParams(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ patientId: "patient-123" }),
  usePathname: () => "/patients/patient-123",
  useSearchParams: () => nav.search,
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
}));
vi.mock("@/lib/hooks/usePageTitle", () => ({ usePageTitle: vi.fn() }));
vi.mock("@/components/AuthGate", () => ({ AuthGate: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock("@/components/LoadingSkeleton", () => ({ LoadingSkeleton: ({ label }: { label: string }) => <div>{label}</div> }));
vi.mock("@/components/StatusBanner", () => ({ StatusBanner: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/AnalysisHero", () => ({ AnalysisHero: ({ run }: { run: AnalysisRunResponse | null }) => <section>{run ? `Latest analysis: ${run.id}` : "No analysis yet"}</section> }));
vi.mock("@/components/SchedulePanel", () => ({ SchedulePanel: () => <section>Schedule</section> }));
vi.mock("@/components/SymptomPanel", () => ({ SymptomPanel: () => <section>Symptom panel</section> }));
vi.mock("@/components/MedicationList", () => ({ MedicationList: () => <section>Medication list</section> }));
vi.mock("@/components/MedicationPicker", () => ({ MedicationPicker: () => <section>Medication form</section> }));
vi.mock("@/components/TimelineList", () => ({ TimelineList: () => <section>Timeline list</section> }));
vi.mock("@/lib/api/patients", () => ({ getPatient: vi.fn() }));
vi.mock("@/lib/api/medications", () => ({ listMedications: vi.fn() }));
vi.mock("@/lib/api/symptoms", () => ({ listSymptoms: vi.fn() }));
vi.mock("@/lib/api/timeline", () => ({ listTimeline: vi.fn() }));
vi.mock("@/lib/api/analysis", () => ({ listAnalysisRuns: vi.fn(), runAnalysis: vi.fn() }));

const patient = { id: "patient-123", user_id: "user-123", name: "Asha Rao", age: 42, sex: "female", weight_kg: 64, renal_flag: false, hepatic_flag: true, created_at: "2026-09-08T10:00:00Z", updated_at: "2026-09-08T10:00:00Z" };
const medication = { id: "med-123", patient_id: "patient-123", drug_id: "drug-123", drug_name: "Aspirin", drug_generic_name: "aspirin", drug_term_type: "IN", drug_source: "RxNorm", condition_id: null, purpose_text: null, dose: "100 mg", times_per_day: 1, interval_hours: null, duration_days: 30, start_date: "2026-09-01", end_date: null, status: "active", created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-01T10:00:00Z" } satisfies MedicationResponse;
const analysis = { id: "analysis-123", patient_id: "patient-123", analysis_version: "1.0", deterministic_result: { safety_score: 82, risk_level: "moderate", starting_score: 100, total_points_deducted: 18, interaction_findings: [], adr_findings: [], adherence_findings: [], penalties: [] }, safety_score: 82, risk_level: "moderate", llm_summary: null, llm_reasoning: null, llm_recommendations: null, confidence_score: null, confidence_level: null, created_at: "2026-09-08T10:00:00Z" } satisfies AnalysisRunResponse;

function setCategory(value: string | null) {
  nav.search = new URLSearchParams(value ? { category: value } : {});
}

describe("PatientPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setCategory(null);
    vi.mocked(getPatient).mockResolvedValue(patient);
    vi.mocked(listMedications).mockResolvedValue([medication]);
    vi.mocked(listSymptoms).mockResolvedValue([]);
    vi.mocked(listTimeline).mockResolvedValue([]);
    vi.mocked(listAnalysisRuns).mockResolvedValueOnce([]).mockResolvedValue([analysis]);
    vi.mocked(runAnalysis).mockResolvedValue(analysis);
  });

  it("loads the patient workspace without exposing internal IDs", async () => {
    render(<PatientPageRoute />);
    expect(screen.getByText("Loading patient")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Asha Rao" })).toBeInTheDocument());
    expect(screen.getByText("42 yrs · female")).toBeInTheDocument();
    expect(screen.getByLabelText("Asha Rao initials")).toBeInTheDocument();
    expect(screen.queryByText("patient-123")).not.toBeInTheDocument();
    expect(screen.getByText("No analysis has been run for this record yet")).toBeInTheDocument();
  });

  it("shows the overview card with every category reachable", async () => {
    render(<PatientPageRoute />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Asha Rao" })).toBeInTheDocument());
    expect(screen.getByRole("region", { name: "Patient workspace" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Safety" })).toBeInTheDocument();
    for (const label of ["Medications", "Symptoms", "Timeline"]) {
      expect(screen.getAllByRole("button", { name: `Show ${label}` }).length).toBeGreaterThan(0);
    }
  });

  it("swaps the previewed category in place without leaving the overview", async () => {
    render(<PatientPageRoute />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Asha Rao" })).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole("button", { name: "Show Medications" })[0]);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Medications" })).toBeInTheDocument());
    expect(screen.getByText("1 active of 1 recorded")).toBeInTheDocument();
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("opens a detail view by putting the category in the URL", async () => {
    render(<PatientPageRoute />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Asha Rao" })).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole("button", { name: "Show Medications" })[0]);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Medications" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Open Medications details" }));
    expect(nav.push).toHaveBeenCalledWith("/patients/patient-123?category=medications");
  });

  it("renders a deep-linked detail view instead of the overview", async () => {
    setCategory("medications");
    render(<PatientPageRoute />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Medications" })).toBeInTheDocument());
    expect(screen.getByText("Medication list")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Patient workspace" })).not.toBeInTheDocument();
  });

  it("falls back to the overview for an unknown category", async () => {
    setCategory("not-a-category");
    render(<PatientPageRoute />);
    await waitFor(() => expect(screen.getByRole("region", { name: "Patient workspace" })).toBeInTheDocument());
  });

  it("returns to the overview from a detail view", async () => {
    setCategory("timeline");
    render(<PatientPageRoute />);
    await waitFor(() => expect(screen.getByText("Timeline list")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Back to overview" }));
    expect(nav.push).toHaveBeenCalledWith("/patients/patient-123");
  });

  it("runs analysis and refreshes the displayed result", async () => {
    render(<PatientPageRoute />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Asha Rao" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Run analysis/ }));
    await waitFor(() => expect(runAnalysis).toHaveBeenCalledWith("patient-123"));
    await waitFor(() =>
      expect(screen.getByText("Safety score 82 of 100 · moderate risk")).toBeInTheDocument(),
    );
  });

  it("keeps the fresh analysis when history refresh returns an older run", async () => {
    const staleHistory: AnalysisRunResponse = { ...analysis, id: "analysis-old", created_at: "2026-09-07T10:00:00Z" };
    vi.mocked(listAnalysisRuns).mockReset();
    vi.mocked(listAnalysisRuns).mockResolvedValueOnce([]).mockResolvedValue([staleHistory]);
    vi.mocked(runAnalysis).mockResolvedValue(analysis);
    render(<PatientPageRoute />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Asha Rao" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Run analysis/ }));
    await waitFor(() => expect(runAnalysis).toHaveBeenCalledWith("patient-123"));
    await waitFor(() => expect(listAnalysisRuns).toHaveBeenCalledTimes(2));
    expect(screen.getByText("Safety score 82 of 100 · moderate risk")).toBeInTheDocument();
    expect(screen.queryByText("analysis-old")).not.toBeInTheDocument();
  });

  it("allows retry after an initial patient load failure", async () => {
    vi.mocked(getPatient).mockRejectedValueOnce(new ApiError(503, "Service unavailable")).mockResolvedValue(patient);
    render(<PatientPageRoute />);
    await waitFor(() => expect(screen.getByText("Service unavailable")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Asha Rao" })).toBeInTheDocument());
    expect(getPatient).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("Service unavailable")).not.toBeInTheDocument();
  });

  it("redirects to login when patient loading returns 401", async () => {
    const location = window.location;
    const assignableLocation = { href: location.href };
    Object.defineProperty(window, "location", { configurable: true, value: assignableLocation });
    vi.mocked(getPatient).mockRejectedValue(new ApiError(401, "Unauthorized"));
    render(<PatientPageRoute />);
    await waitFor(() => expect(window.location.href).toBe("/login"));
    Object.defineProperty(window, "location", { configurable: true, value: location });
  });
});
