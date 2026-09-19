import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SchedulePanel } from "@/components/SchedulePanel";
import { ApiError } from "@/lib/api/errors";

const { displayDrugName, generateMedicationSchedule, listUpcomingDoses, markDose } = vi.hoisted(() => ({
  displayDrugName: vi.fn(),
  generateMedicationSchedule: vi.fn(),
  listUpcomingDoses: vi.fn(),
  markDose: vi.fn(),
}));

vi.mock("@/lib/api/schedule", () => ({
  generateMedicationSchedule,
  listUpcomingDoses,
  markDose,
}));

vi.mock("@/lib/drugs/nameCache", () => ({
  displayDrugName,
}));

const medication = {
  id: "medication-1",
  patient_id: "patient-1",
  condition_id: null,
  purpose_text: null,
  drug_id: "drug-1",
  dose: "500 mg",
  times_per_day: 2,
  interval_hours: null,
  duration_days: 7,
  status: "active" as const,
  start_date: "2026-09-07",
  end_date: null,
  created_at: "2026-09-07T08:00:00Z",
  updated_at: "2026-09-07T08:00:00Z",
  drug_name: null,
  drug_generic_name: null,
  drug_term_type: null,
  drug_source: null,
};

const dose = {
  id: "dose-1",
  medication_id: "medication-1",
  scheduled_time: "2026-09-08T10:30:00Z",
  drug_name: "Examplecin",
  dose: "500 mg",
};

describe("SchedulePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    displayDrugName.mockReturnValue({ name: "Examplecin", cached: true, termType: "IN" });
    listUpcomingDoses.mockResolvedValue([dose]);
    generateMedicationSchedule.mockResolvedValue([]);
    markDose.mockResolvedValue({ ...dose, status: "taken", actual_time: "2026-09-08T10:30:00Z" });
  });

  it("loads upcoming doses and marks a dose as taken", async () => {
    const user = userEvent.setup();
    render(<SchedulePanel patientId="patient-1" medications={[medication]} />);

    expect(await screen.findByText("Examplecin")).toBeInTheDocument();
    expect(listUpcomingDoses).toHaveBeenCalledWith("patient-1");

    await user.click(screen.getByRole("button", { name: "Taken Examplecin dose" }));

    await waitFor(() => {
      expect(markDose).toHaveBeenCalledWith("dose-1", { status: "taken" });
    });
    expect(listUpcomingDoses).toHaveBeenCalledTimes(2);
  });

  it("creates a schedule for an eligible active medication without exposing its id", async () => {
    const user = userEvent.setup();
    listUpcomingDoses.mockResolvedValue([]);
    displayDrugName.mockReturnValue({ name: "Examplecin", cached: true, termType: "IN" });
    render(<SchedulePanel patientId="patient-1" medications={[medication]} />);

    expect(await screen.findByText("No upcoming doses")).toBeInTheDocument();
    expect(screen.getByText("Examplecin")).toBeInTheDocument();
    expect(screen.queryByText(/medication-1/)).not.toBeInTheDocument();
    expect(displayDrugName).toHaveBeenCalledWith("drug-1");

    await user.click(screen.getByRole("button", { name: "Create schedule for Examplecin" }));

    await waitFor(() => {
      expect(generateMedicationSchedule).toHaveBeenCalledWith("medication-1");
    });
    expect(await screen.findByText(/Schedule generated/)).toBeInTheDocument();
  });

  it("uses the honest uncached label when the drug name is unavailable", async () => {
    listUpcomingDoses.mockResolvedValue([]);
    displayDrugName.mockReturnValue({ name: "Name not cached in this browser", cached: false, termType: null });
    render(<SchedulePanel patientId="patient-1" medications={[medication]} />);

    expect(await screen.findByText("Name not cached in this browser")).toBeInTheDocument();
    expect(screen.queryByText(/drug-1/)).not.toBeInTheDocument();
    expect(screen.queryByText(/medication-1/)).not.toBeInTheDocument();
  });

  it.each([
    { name: "doses", response: [dose] },
    { name: "an empty schedule", response: [] },
  ])("shows only the request error and recovers to $name on refresh", async ({ response }) => {
    const user = userEvent.setup();
    listUpcomingDoses.mockRejectedValueOnce(new ApiError(503, "Could not load upcoming doses."));
    render(<SchedulePanel patientId="patient-1" medications={[medication]} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load upcoming doses.");
    expect(screen.queryByText("No upcoming doses")).not.toBeInTheDocument();

    listUpcomingDoses.mockResolvedValue(response);
    await user.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    if (response.length > 0) {
      expect(screen.getByRole("button", { name: "Taken Examplecin dose" })).toBeInTheDocument();
      expect(screen.queryByText("No upcoming doses")).not.toBeInTheDocument();
    } else {
      expect(screen.getByText("No upcoming doses")).toBeInTheDocument();
    }
    expect(listUpcomingDoses).toHaveBeenCalledTimes(2);
  });

  it("hides a previously empty schedule when its refresh fails", async () => {
    const user = userEvent.setup();
    listUpcomingDoses.mockResolvedValueOnce([]);
    render(<SchedulePanel patientId="patient-1" medications={[medication]} />);
    expect(await screen.findByText("No upcoming doses")).toBeInTheDocument();

    listUpcomingDoses.mockRejectedValueOnce(new ApiError(503, "Could not load upcoming doses."));
    await user.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load upcoming doses.");
    expect(screen.queryByText("No upcoming doses")).not.toBeInTheDocument();
  });

  it("keeps previously loaded doses visible when their refresh fails", async () => {
    const user = userEvent.setup();
    render(<SchedulePanel patientId="patient-1" medications={[medication]} />);
    expect(await screen.findByRole("button", { name: "Taken Examplecin dose" })).toBeInTheDocument();

    listUpcomingDoses.mockRejectedValueOnce(new ApiError(503, "Could not load upcoming doses."));
    await user.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load upcoming doses.");
    expect(screen.getByRole("button", { name: "Taken Examplecin dose" })).toBeInTheDocument();
    expect(screen.queryByText("No upcoming doses")).not.toBeInTheDocument();
  });
});
