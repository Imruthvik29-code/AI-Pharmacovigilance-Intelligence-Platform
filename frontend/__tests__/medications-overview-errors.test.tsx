import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PatientPageRoute from "@/app/patients/[patientId]/page";
import { ApiError } from "@/lib/api/errors";
import { getPatient } from "@/lib/api/patients";
import { listMedications } from "@/lib/api/medications";
import { listSymptoms } from "@/lib/api/symptoms";
import { listTimeline } from "@/lib/api/timeline";
import { listAnalysisRuns } from "@/lib/api/analysis";
import type { MedicationResponse, PatientResponse } from "@/lib/api/types";

const push = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useParams: () => ({ patientId: "patient-123" }),
  usePathname: () => "/patients/patient-123",
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push, replace: vi.fn() }),
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
  relation: null, timezone: null, breakfast_time: null, lunch_time: null,
  dinner_time: null, created_at: "2026-09-08T10:00:00Z", updated_at: "2026-09-08T10:00:00Z",
};
const medication: MedicationResponse = {
  id: "med-123", patient_id: patient.id, drug_id: "drug-123", drug_name: "Aspirin",
  drug_generic_name: "aspirin", drug_term_type: "IN", drug_source: "RxNorm",
  condition_id: null, purpose_text: null, dose: "100 mg", times_per_day: 1,
  interval_hours: null, duration_days: 30, start_date: "2026-09-01", end_date: null,
  status: "active", created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-01T10:00:00Z",
};

function openMedicationCard() {
  fireEvent.click(screen.getByRole("button", { name: "Show Medications" }));
  return within(screen.getByRole("heading", { name: "Medications" }).closest("article")!);
}

describe("Overview medication request states", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(getPatient).mockResolvedValue(patient);
    vi.mocked(listSymptoms).mockResolvedValue([]);
    vi.mocked(listTimeline).mockResolvedValue([]);
    vi.mocked(listAnalysisRuns).mockResolvedValue([]);
  });

  it("reports a failed request in the hero and card without claiming an empty record", async () => {
    vi.mocked(listMedications).mockRejectedValue(new ApiError(500, "Request failed (500)."));
    render(<PatientPageRoute />);

    await screen.findAllByText("Medication data unavailable");
    expect(screen.queryByText("No medications recorded")).not.toBeInTheDocument();
    expect(screen.queryByText("0 active of 0 recorded")).not.toBeInTheDocument();
    const card = openMedicationCard();
    expect(card.getByText("Medication data unavailable")).toBeInTheDocument();
    expect(card.getByText("Request failed (500).")).toBeInTheDocument();
    fireEvent.click(card.getByRole("button", { name: "Open Medications details" }));
    expect(push).toHaveBeenCalledWith("/patients/patient-123?category=medications");
  });

  it("keeps the legitimate empty state when the request succeeds with no records", async () => {
    vi.mocked(listMedications).mockResolvedValue([]);
    render(<PatientPageRoute />);

    await screen.findAllByText("No medications recorded");
    const card = openMedicationCard();
    expect(card.getByText("No medications recorded")).toBeInTheDocument();
    expect(screen.queryByText("Medication data unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("Request failed (500).")).not.toBeInTheDocument();
  });

  it("preserves recorded counts and names when medication data loads", async () => {
    vi.mocked(listMedications).mockResolvedValue([medication]);
    render(<PatientPageRoute />);

    await screen.findByText("1 of 1 medications");
    const card = openMedicationCard();
    expect(card.getByText("1 active of 1 recorded")).toBeInTheDocument();
    expect(card.getByText("Aspirin")).toBeInTheDocument();
    expect(screen.queryByText("Medication data unavailable")).not.toBeInTheDocument();
    expect(screen.queryByText("No medications recorded")).not.toBeInTheDocument();
  });
});
