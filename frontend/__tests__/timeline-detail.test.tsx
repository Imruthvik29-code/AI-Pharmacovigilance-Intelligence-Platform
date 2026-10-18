import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PatientPageRoute from "@/app/patients/[patientId]/page";
import { getPatient } from "@/lib/api/patients";
import { listMedications } from "@/lib/api/medications";
import { listSymptoms } from "@/lib/api/symptoms";
import { listTimeline } from "@/lib/api/timeline";
import { listAnalysisRuns } from "@/lib/api/analysis";
import { ApiError } from "@/lib/api/errors";
import type { TimelineEventResponse } from "@/lib/api/types";

vi.mock("next/navigation", () => ({
  useParams: () => ({ patientId: "patient-123" }),
  usePathname: () => "/patients/patient-123",
  useSearchParams: () => new URLSearchParams({ category: "timeline" }),
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

const patient = { id: "patient-123", user_id: "user-123", name: "Asha Rao", age: 42, sex: "female", weight_kg: 64, renal_flag: false, hepatic_flag: false, timezone: null, breakfast_time: null, lunch_time: null, dinner_time: null, created_at: "2026-09-08T10:00:00Z", updated_at: "2026-09-08T10:00:00Z" };
const recorded: TimelineEventResponse = { id: "ev-1", patient_id: "patient-123", event_type: "medication_started", ref_id: "med-1", event_title: "Started Aspirin 81 MG Oral Tablet", event_description: "1 tablet", event_time: "2026-09-10T08:00:00Z", payload: null, created_at: "2026-09-10T08:00:00Z" };

describe("Timeline detail route", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(getPatient).mockResolvedValue(patient);
    vi.mocked(listMedications).mockResolvedValue([]);
    vi.mocked(listSymptoms).mockResolvedValue([]);
    vi.mocked(listAnalysisRuns).mockResolvedValue([]);
  });

  it("holds the empty state while this patient's timeline is loading", async () => {
    let resolveRequest!: (value: TimelineEventResponse[]) => void;
    vi.mocked(listTimeline).mockReturnValue(new Promise((resolve) => { resolveRequest = resolve; }));
    render(<PatientPageRoute />);

    await waitFor(() => expect(listTimeline).toHaveBeenCalledWith("patient-123"));
    expect(screen.getByRole("heading", { level: 1, name: "Timeline" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Loading timeline" })).toBeInTheDocument();
    expect(screen.queryByText("No events recorded yet")).not.toBeInTheDocument();

    await act(async () => { resolveRequest([recorded]); });

    expect(await screen.findByText("Started Aspirin 81 MG Oral Tablet")).toBeInTheDocument();
    expect(screen.getByText("1 event")).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Loading timeline" })).not.toBeInTheDocument();
  });

  it("retries only the timeline after a failed request", async () => {
    vi.mocked(listTimeline)
      .mockRejectedValueOnce(new ApiError(503, "Timeline is temporarily unavailable."))
      .mockResolvedValueOnce([recorded]);
    render(<PatientPageRoute />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Timeline is temporarily unavailable.");
    expect(screen.queryByText("No events recorded yet")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Started Aspirin 81 MG Oral Tablet")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(listTimeline).toHaveBeenCalledTimes(2);
    expect(listTimeline).toHaveBeenLastCalledWith("patient-123");
    expect(listAnalysisRuns).toHaveBeenCalledTimes(1);
    expect(getPatient).toHaveBeenCalledTimes(1);
  });

  it("shows the empty state once an empty timeline arrives", async () => {
    vi.mocked(listTimeline).mockResolvedValue([]);
    render(<PatientPageRoute />);
    expect(await screen.findByText("No events recorded yet")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
