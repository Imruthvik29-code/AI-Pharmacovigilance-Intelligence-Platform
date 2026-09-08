import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PatientPage from "@/app/patients/[patientId]/page";
import { ApiError } from "@/lib/api/errors";
import { getPatient } from "@/lib/api/patients";
import { listMedications } from "@/lib/api/medications";
import { listSymptoms } from "@/lib/api/symptoms";
import { listTimeline } from "@/lib/api/timeline";
import { listAnalysisRuns, runAnalysis } from "@/lib/api/analysis";
import type { AnalysisRunResponse, MedicationResponse } from "@/lib/api/types";

vi.mock("next/navigation", () => ({
  useParams: () => ({ patientId: "patient-123" }),
}));

vi.mock("@/lib/hooks/usePageTitle", () => ({
  usePageTitle: vi.fn(),
}));

vi.mock("@/components/AuthGate", () => ({
  AuthGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));

vi.mock("@/components/LoadingSkeleton", () => ({
  LoadingSkeleton: ({ label }: { label: string }) => <div>{label}</div>,
}));

vi.mock("@/components/StatusBanner", () => ({
  StatusBanner: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/AnalysisHero", () => ({
  AnalysisHero: ({ run }: { run: unknown }) => <section>{run ? "Latest analysis available" : "No analysis yet"}</section>,
}));

vi.mock("@/components/SchedulePanel", () => ({
  SchedulePanel: () => <section>Schedule</section>,
}));

vi.mock("@/components/SymptomPanel", () => ({
  SymptomPanel: () => <section>Symptoms</section>,
}));

vi.mock("@/components/MedicationList", () => ({
  MedicationList: () => <section>Medications</section>,
}));

vi.mock("@/components/MedicationPicker", () => ({
  MedicationPicker: () => <section>Medication form</section>,
}));

vi.mock("@/components/TimelineList", () => ({
  TimelineList: () => <section>Timeline</section>,
}));

vi.mock("@/lib/api/patients", () => ({
  getPatient: vi.fn(),
}));

vi.mock("@/lib/api/medications", () => ({
  listMedications: vi.fn(),
}));

vi.mock("@/lib/api/symptoms", () => ({
  listSymptoms: vi.fn(),
}));

vi.mock("@/lib/api/timeline", () => ({
  listTimeline: vi.fn(),
}));

vi.mock("@/lib/api/analysis", () => ({
  listAnalysisRuns: vi.fn(),
  runAnalysis: vi.fn(),
}));

const patient = {
  id: "patient-123",
  user_id: "user-123",
  name: "Asha Rao",
  age: 42,
  sex: "female",
  weight_kg: 64,
  renal_flag: false,
  hepatic_flag: true,
  created_at: "2026-09-08T10:00:00Z",
  updated_at: "2026-09-08T10:00:00Z",
};

const medication = {
  id: "med-123",
  patient_id: "patient-123",
  drug_id: "drug-123",
  drug_name: "Aspirin",
  drug_generic_name: "aspirin",
  drug_term_type: "IN",
  drug_source: "RxNorm",
  condition_id: null,
  purpose_text: null,
  dose: "100 mg",
  dosage: "100 mg",
  frequency: "once daily",
  times_per_day: 1,
  interval_hours: null,
  duration_days: 30,
  start_date: "2026-09-01",
  end_date: null,
  status: "active",
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
} satisfies MedicationResponse;

const analysis = {
  id: "analysis-123",
  patient_id: "patient-123",
  analysis_version: "1.0",
  deterministic_result: {
    safety_score: 82,
    risk_level: "moderate",
    starting_score: 100,
    total_points_deducted: 18,
    interaction_findings: [],
    adr_findings: [],
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
  created_at: "2026-09-08T10:00:00Z",
} satisfies AnalysisRunResponse;

describe("PatientPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getPatient).mockResolvedValue(patient);
    vi.mocked(listMedications).mockResolvedValue([medication]);
    vi.mocked(listSymptoms).mockResolvedValue([]);
    vi.mocked(listTimeline).mockResolvedValue([]);
    vi.mocked(listAnalysisRuns).mockResolvedValue([]);
    vi.mocked(runAnalysis).mockResolvedValue(analysis);
  });

  it("loads the patient workspace without exposing internal IDs", async () => {
    render(<PatientPage />);

    expect(screen.getByText("Loading patient")).toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole("heading", { name: "Asha Rao" })).toBeInTheDocument());

    expect(screen.getByText("Age 42 · female · 64 kg · Hepatic flag")).toBeInTheDocument();
    expect(screen.getByText("1 medications")).toBeInTheDocument();
    expect(screen.getByText("1 active")).toBeInTheDocument();
    expect(screen.queryByText("patient-123")).not.toBeInTheDocument();
    expect(screen.getByText("No analysis yet")).toBeInTheDocument();
  });

  it("runs analysis and refreshes the displayed result", async () => {
    render(<PatientPage />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Asha Rao" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));

    await waitFor(() => expect(runAnalysis).toHaveBeenCalledWith("patient-123"));
    await waitFor(() => expect(screen.getByText("Latest analysis available")).toBeInTheDocument());
  });

  it("redirects to login when patient loading returns 401", async () => {
    const location = window.location;
    const assignableLocation = { href: location.href };
    Object.defineProperty(window, "location", { configurable: true, value: assignableLocation });
    vi.mocked(getPatient).mockRejectedValue(new ApiError(401, "Unauthorized"));

    render(<PatientPage />);

    await waitFor(() => expect(window.location.href).toBe("/login"));

    Object.defineProperty(window, "location", { configurable: true, value: location });
  });
});
