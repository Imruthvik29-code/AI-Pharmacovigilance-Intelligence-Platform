import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PatientPageRoute from "@/app/patients/[patientId]/page";
import { getPatient } from "@/lib/api/patients";
import { listMedications } from "@/lib/api/medications";
import { listSymptoms } from "@/lib/api/symptoms";
import { listTimeline } from "@/lib/api/timeline";
import { listAnalysisRuns } from "@/lib/api/analysis";
import { ApiError } from "@/lib/api/errors";
import type { SymptomResponse } from "@/lib/api/types";

vi.mock("next/navigation", () => ({
  useParams: () => ({ patientId: "patient-123" }),
  usePathname: () => "/patients/patient-123",
  useSearchParams: () => new URLSearchParams({ category: "symptoms" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("@/components/AuthGate", () => ({
  AuthGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("@/lib/api/patients", () => ({ getPatient: vi.fn() }));
vi.mock("@/lib/api/medications", () => ({ listMedications: vi.fn() }));
vi.mock("@/lib/api/symptoms", () => ({ listSymptoms: vi.fn(), createSymptom: vi.fn() }));
vi.mock("@/lib/api/timeline", () => ({ listTimeline: vi.fn() }));
vi.mock("@/lib/api/analysis", () => ({ listAnalysisRuns: vi.fn(), runAnalysis: vi.fn() }));

const patient = { id: "patient-123", user_id: "user-123", name: "Asha Rao", age: 42, sex: "female", weight_kg: 64, renal_flag: false, hepatic_flag: false, timezone: null, breakfast_time: null, lunch_time: null, dinner_time: null, created_at: "2026-09-08T10:00:00Z", updated_at: "2026-09-08T10:00:00Z" };
const recorded: SymptomResponse = { id: "sym-1", patient_id: "patient-123", condition_id: null, medication_id: null, description: "Nausea in the morning", severity: "moderate", onset_date: "2026-09-10", resolved_date: null, created_at: "2026-09-10T08:00:00Z", updated_at: "2026-09-10T08:00:00Z" };

describe("Symptoms detail route", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(getPatient).mockResolvedValue(patient);
    vi.mocked(listMedications).mockResolvedValue([]);
    vi.mocked(listTimeline).mockResolvedValue([]);
    vi.mocked(listAnalysisRuns).mockResolvedValue([]);
  });

  it("loads this patient's symptoms and holds the empty state until they arrive", async () => {
    let resolveRequest!: (value: SymptomResponse[]) => void;
    vi.mocked(listSymptoms).mockReturnValue(new Promise((resolve) => { resolveRequest = resolve; }));
    render(<PatientPageRoute />);

    await waitFor(() => expect(listSymptoms).toHaveBeenCalledWith("patient-123"));
    expect(screen.getByRole("heading", { level: 1, name: "Symptoms" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Loading symptoms" })).toBeInTheDocument();
    expect(screen.queryByText("No symptoms recorded")).not.toBeInTheDocument();

    await act(async () => { resolveRequest([recorded]); });

    expect(await screen.findByRole("heading", { level: 3, name: "Nausea in the morning" })).toBeInTheDocument();
    expect(screen.getByText("1 unresolved of 1 reported")).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Loading symptoms" })).not.toBeInTheDocument();
  });

  it("retries a failed symptom request without reloading the rest of the record", async () => {
    vi.mocked(listSymptoms)
      .mockRejectedValueOnce(new ApiError(503, "Symptoms are temporarily unavailable."))
      .mockResolvedValueOnce([recorded]);
    render(<PatientPageRoute />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Symptoms are temporarily unavailable.");
    expect(screen.queryByText("No symptoms recorded")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { level: 3, name: "Nausea in the morning" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(listSymptoms).toHaveBeenCalledTimes(2);
    expect(listSymptoms).toHaveBeenLastCalledWith("patient-123");
    expect(getPatient).toHaveBeenCalledTimes(1);
    expect(listMedications).toHaveBeenCalledTimes(1);
  });

  it("shows the empty state once an empty list arrives", async () => {
    vi.mocked(listSymptoms).mockResolvedValue([]);
    render(<PatientPageRoute />);
    expect(await screen.findByText("No symptoms recorded")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
