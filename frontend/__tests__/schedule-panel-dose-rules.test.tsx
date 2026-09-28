import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SchedulePanel } from "@/components/SchedulePanel";
import type { DoseRuleResponse, MedicationResponse, PatientResponse } from "@/lib/api/types";

const { displayDrugName, generateMedicationSchedule, listUpcomingDoses, markDose } = vi.hoisted(() => ({
  displayDrugName: vi.fn(),
  generateMedicationSchedule: vi.fn(),
  listUpcomingDoses: vi.fn(),
  markDose: vi.fn(),
}));

vi.mock("@/lib/api/schedule", () => ({ generateMedicationSchedule, listUpcomingDoses, markDose }));
vi.mock("@/lib/drugs/nameCache", () => ({ displayDrugName }));

const patient: PatientResponse = {
  id: "p1", user_id: "u1", name: "Asha", relation: null, age: null, sex: null, weight_kg: null,
  renal_flag: false, hepatic_flag: false, timezone: "Asia/Kolkata",
  breakfast_time: "08:00:00", lunch_time: null, dinner_time: "20:00:00",
  created_at: "", updated_at: "",
};

const rule = (sequence: number, over: Partial<DoseRuleResponse> = {}): DoseRuleResponse => ({
  id: `r${sequence}`, medication_id: "m1", sequence, anchor_type: "breakfast",
  anchor_relation: "with", offset_minutes: null, clock_time: null, dose: null,
  created_at: "", updated_at: "", ...over,
});

const med = (over: Partial<MedicationResponse>): MedicationResponse => ({
  id: "m1", patient_id: "p1", condition_id: null, purpose_text: null, drug_id: "d1",
  dose: "1 tablet", times_per_day: 2, interval_hours: null, duration_days: 5,
  status: "active", start_date: "2026-10-01", end_date: null, created_at: "", updated_at: "",
  drug_name: "Examplecin", drug_generic_name: null, drug_term_type: null, drug_source: null,
  ...over,
});

describe("SchedulePanel with dose timing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    displayDrugName.mockReturnValue({ name: "Examplecin", cached: true, termType: null });
    listUpcomingDoses.mockResolvedValue([]);
  });

  it("holds back a course whose timing is incomplete, and says why", async () => {
    render(<SchedulePanel patientId="p1" medications={[med({ dose_rules: [rule(1)] })]} patient={patient} />);
    expect(await screen.findByText("1 of 2 dose timings set.")).toBeInTheDocument();
    expect(screen.getByText("Not yet schedulable")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create schedule/i })).not.toBeInTheDocument();
  });

  it("names a meal missing from the routine instead of offering to schedule", async () => {
    render(
      <SchedulePanel patientId="p1" patient={patient}
        medications={[med({ times_per_day: 1, dose_rules: [rule(1, { anchor_type: "lunch" })] })]} />,
    );
    expect(await screen.findByText(/Lunch time is not recorded/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create schedule/i })).not.toBeInTheDocument();
  });

  it("offers Create schedule once timing, frequency and routine agree", async () => {
    render(
      <SchedulePanel patientId="p1" patient={patient}
        medications={[med({ dose_rules: [rule(1), rule(2, { anchor_type: "dinner" })] })]} />,
    );
    expect(await screen.findByRole("button", { name: "Create schedule for Examplecin" })).toBeInTheDocument();
  });

  it("uses accurate copy when a course is blocked on timing rather than frequency", async () => {
    render(<SchedulePanel patientId="p1" medications={[med({ dose_rules: [rule(1)] })]} patient={patient} />);
    expect(await screen.findByText(/No active medication is ready to schedule yet/)).toBeInTheDocument();
    expect(screen.queryByText(/has both a recorded duration and dosing frequency/)).not.toBeInTheDocument();
  });

  it("keeps the original wording when the only blockers are duration and frequency", async () => {
    render(<SchedulePanel patientId="p1" patient={patient}
      medications={[med({ times_per_day: null, duration_days: null })]} />);
    expect(await screen.findByText(/has both a recorded duration and dosing frequency/)).toBeInTheDocument();
    expect(screen.getByText(/A schedule needs the prescribed duration and frequency/)).toBeInTheDocument();
  });

  it("marks a course with upcoming doses as scheduled instead of offering Create again", async () => {
    listUpcomingDoses.mockResolvedValue([
      { id: "d1", medication_id: "m1", scheduled_time: "2099-01-01T08:00:00Z", drug_name: "Examplecin", dose: "1 tablet" },
    ]);
    render(<SchedulePanel patientId="p1" patient={patient}
      medications={[med({ dose_rules: [rule(1), rule(2, { anchor_type: "dinner" })] })]} />);
    expect(await screen.findByText("Schedule created")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create schedule/i })).not.toBeInTheDocument();
  });

  it("never generates a schedule on its own", async () => {
    render(<SchedulePanel patientId="p1" patient={patient}
      medications={[med({ dose_rules: [rule(1), rule(2, { anchor_type: "dinner" })] })]} />);
    await screen.findByRole("button", { name: "Create schedule for Examplecin" });
    expect(generateMedicationSchedule).not.toHaveBeenCalled();
  });
});
