import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PatientPageRoute from "@/app/patients/[patientId]/page";
import { getPatient } from "@/lib/api/patients";
import { listMedications } from "@/lib/api/medications";
import { listSymptoms } from "@/lib/api/symptoms";
import { listTimeline } from "@/lib/api/timeline";
import { listAnalysisRuns } from "@/lib/api/analysis";
import type { MedicationResponse } from "@/lib/api/types";

vi.mock("next/navigation", () => ({
  useParams: () => ({ patientId: "patient-123" }),
  usePathname: () => "/patients/patient-123",
  useSearchParams: () => new URLSearchParams({ category: "medications" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("@/components/AuthGate", () => ({
  AuthGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("@/components/SchedulePanel", () => ({ SchedulePanel: () => null }));
vi.mock("@/lib/api/patients", () => ({ getPatient: vi.fn() }));
vi.mock("@/lib/api/medications", () => ({ listMedications: vi.fn() }));
vi.mock("@/lib/api/symptoms", () => ({ listSymptoms: vi.fn() }));
vi.mock("@/lib/api/timeline", () => ({ listTimeline: vi.fn() }));
vi.mock("@/lib/api/analysis", () => ({ listAnalysisRuns: vi.fn(), runAnalysis: vi.fn() }));

const patient = { id: "patient-123", user_id: "user-123", name: "Asha Rao", age: 42, sex: "female", weight_kg: 64, renal_flag: false, hepatic_flag: true, created_at: "2026-09-08T10:00:00Z", updated_at: "2026-09-08T10:00:00Z" };
const medication = { id: "med-123", patient_id: "patient-123", drug_id: "drug-123", drug_name: "Aspirin", drug_generic_name: "aspirin", drug_term_type: "IN", drug_source: "RxNorm", condition_id: null, purpose_text: null, dose: "100 mg", times_per_day: 1, interval_hours: null, duration_days: 30, start_date: "2026-09-01", end_date: null, status: "active", created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-01T10:00:00Z" } satisfies MedicationResponse;

describe("Medications detail loading", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(getPatient).mockResolvedValue(patient);
    vi.mocked(listSymptoms).mockResolvedValue([]);
    vi.mocked(listTimeline).mockResolvedValue([]);
    vi.mocked(listAnalysisRuns).mockResolvedValue([]);
  });

  it.each([
    { name: "populated", medications: [medication] },
    { name: "empty", medications: [] },
  ])("keeps the $name response pending until the medication request settles", async ({ medications }) => {
    let resolveRequest!: (value: MedicationResponse[]) => void;
    vi.mocked(listMedications).mockReturnValue(new Promise((resolve) => { resolveRequest = resolve; }));
    render(<PatientPageRoute />);

    try {
      await waitFor(() => expect(listMedications).toHaveBeenCalledWith("patient-123"));
      expect(screen.getByRole("status", { name: "Loading medications" })).toBeInTheDocument();
      expect(screen.queryByText("No medications recorded")).not.toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "Aspirin" })).not.toBeInTheDocument();
    } finally {
      await act(async () => { resolveRequest(medications); });
    }

    await waitFor(() => expect(screen.queryByRole("status", { name: "Loading medications" })).not.toBeInTheDocument());
    if (medications.length > 0) {
      expect(screen.getByRole("heading", { name: "Aspirin" })).toBeInTheDocument();
      expect(screen.queryByText("No medications recorded")).not.toBeInTheDocument();
    } else {
      expect(screen.getByText("No medications recorded")).toBeInTheDocument();
    }
    expect(listMedications).toHaveBeenCalledTimes(1);
  });
});
