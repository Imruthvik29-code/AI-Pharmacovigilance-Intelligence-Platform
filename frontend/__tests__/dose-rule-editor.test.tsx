import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MedicationList } from "@/components/MedicationList";
import type { DoseRuleResponse, MedicationResponse, PatientResponse } from "@/lib/api/types";

const { updateMedication, generateMedicationSchedule, displayDrugName } = vi.hoisted(() => ({
  updateMedication: vi.fn(),
  generateMedicationSchedule: vi.fn(),
  displayDrugName: vi.fn(),
}));

vi.mock("@/lib/api/medications", () => ({ updateMedication }));
vi.mock("@/lib/api/schedule", () => ({ generateMedicationSchedule }));
vi.mock("@/lib/drugs/nameCache", () => ({ displayDrugName }));

const patient: PatientResponse = {
  id: "p1", user_id: "u1", name: "Asha", relation: null, age: null, sex: null, weight_kg: null,
  renal_flag: false, hepatic_flag: false, timezone: "Asia/Kolkata",
  breakfast_time: "08:00:00", lunch_time: null, dinner_time: "20:00:00",
  created_at: "", updated_at: "",
};

function rule(sequence: number, over: Partial<DoseRuleResponse> = {}): DoseRuleResponse {
  return {
    id: `r${sequence}`, medication_id: "m1", sequence, anchor_type: "breakfast",
    anchor_relation: "with", offset_minutes: null, clock_time: null, dose: null,
    created_at: "", updated_at: "", ...over,
  };
}

function med(over: Partial<MedicationResponse> = {}): MedicationResponse {
  return {
    id: "m1", patient_id: "p1", condition_id: null, purpose_text: null, drug_id: "d1",
    dose: "1 tablet", times_per_day: 2, interval_hours: null, duration_days: 5,
    status: "active", start_date: "2026-10-01", end_date: null, created_at: "", updated_at: "",
    drug_name: "Examplecin", drug_generic_name: null, drug_term_type: null, drug_source: null,
    dose_rules: [], ...over,
  };
}

function renderList(medication: MedicationResponse, onUpdated = vi.fn()) {
  render(<MedicationList medications={[medication]} patient={patient} onMedicationUpdated={onUpdated} />);
  return onUpdated;
}

async function openEditor(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /(set|edit) dose timing for examplecin/i }));
}

describe("dose timing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    displayDrugName.mockReturnValue({ name: "Examplecin", cached: true, termType: null });
    updateMedication.mockImplementation(async (id: string, payload: { dose_rules: unknown[] }) =>
      med({ id, dose_rules: (payload.dose_rules as Array<Record<string, unknown>>).map((r, i) => rule(i + 1, r as Partial<DoseRuleResponse>)) }));
  });

  it("offers no editor when the rules were not loaded", () => {
    renderList(med({ dose_rules: undefined }));
    expect(screen.queryByRole("region", { name: "Dose timing" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /dose timing/i })).not.toBeInTheDocument();
  });

  it("stays read-only when no update handler is supplied", () => {
    render(<MedicationList medications={[med({ dose_rules: [rule(1)] })]} />);
    expect(screen.queryByRole("region", { name: "Dose timing" })).not.toBeInTheDocument();
  });

  it("summarises saved rules, including a per-dose amount override", () => {
    renderList(med({
      dose_rules: [
        rule(1, { anchor_relation: "before", offset_minutes: 30 }),
        rule(2, { anchor_type: "dinner", dose: "half tablet" }),
      ],
    }));
    const region = screen.getByRole("region", { name: "Dose timing" });
    expect(within(region).getByText(/30 min before breakfast/)).toBeInTheDocument();
    expect(within(region).getByText(/With dinner/)).toBeInTheDocument();
    expect(within(region).getByText(/half tablet/)).toBeInTheDocument();
  });

  it("explains that interval courses do not use dose timing", () => {
    renderList(med({ times_per_day: null, interval_hours: 8 }));
    expect(screen.getByText(/Scheduled every 8 h, so dose timing isn't used/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /dose timing/i })).not.toBeInTheDocument();
  });

  it("adds a rule with nothing assumed and blocks saving until it is complete", async () => {
    const user = userEvent.setup();
    renderList(med());
    await openEditor(user);
    await user.click(screen.getByRole("button", { name: "Add dose timing" }));

    expect(screen.getByLabelText("When")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Save dose timing" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Dose 1: Choose when/);
    expect(updateMedication).not.toHaveBeenCalled();
  });

  it("shows relation and offset only for meal anchors, and validates 1-60", async () => {
    const user = userEvent.setup();
    renderList(med());
    await openEditor(user);
    await user.click(screen.getByRole("button", { name: "Add dose timing" }));

    await user.selectOptions(screen.getByLabelText("When"), "dinner");
    await user.selectOptions(screen.getByLabelText("Timing"), "after");
    const minutes = screen.getByLabelText("Minutes");
    await user.type(minutes, "61");
    await user.click(screen.getByRole("button", { name: "Save dose timing" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/1–60 minutes/);
    expect(updateMedication).not.toHaveBeenCalled();

    await user.clear(minutes);
    await user.type(minutes, "45");
    await user.click(screen.getByRole("button", { name: "Save dose timing" }));
    await waitFor(() => expect(updateMedication).toHaveBeenCalled());
    expect(updateMedication.mock.calls[0][1]).toEqual({
      dose_rules: [{ sequence: 1, anchor_type: "dinner", anchor_relation: "after", offset_minutes: 45, dose: null }],
    });
  });

  it("uses a clock time with no relation or offset, and drops a stale offset", async () => {
    const user = userEvent.setup();
    renderList(med());
    await openEditor(user);
    await user.click(screen.getByRole("button", { name: "Add dose timing" }));

    await user.selectOptions(screen.getByLabelText("When"), "breakfast");
    await user.selectOptions(screen.getByLabelText("Timing"), "before");
    await user.type(screen.getByLabelText("Minutes"), "20");
    await user.selectOptions(screen.getByLabelText("When"), "clock_time");

    expect(screen.queryByLabelText("Timing")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Minutes")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Time"), "21:00");
    await user.click(screen.getByRole("button", { name: "Save dose timing" }));

    await waitFor(() => expect(updateMedication).toHaveBeenCalled());
    expect(updateMedication.mock.calls[0][1]).toEqual({
      dose_rules: [{ sequence: 1, anchor_type: "clock_time", clock_time: "21:00", dose: null }],
    });
  });

  it("sends only dose_rules, with contiguous sequences after reordering", async () => {
    const user = userEvent.setup();
    renderList(med({ dose_rules: [rule(1), rule(2, { anchor_type: "dinner" })] }));
    await openEditor(user);
    await user.click(screen.getByRole("button", { name: "Move dose 2 earlier" }));
    await user.click(screen.getByRole("button", { name: "Save dose timing" }));

    await waitFor(() => expect(updateMedication).toHaveBeenCalled());
    const payload = updateMedication.mock.calls[0][1];
    expect(Object.keys(payload)).toEqual(["dose_rules"]);
    expect(payload.dose_rules.map((r: { sequence: number; anchor_type: string }) => [r.sequence, r.anchor_type]))
      .toEqual([[1, "dinner"], [2, "breakfast"]]);
  });

  it("clears all rules with an explicit empty list, never null", async () => {
    const user = userEvent.setup();
    renderList(med({ dose_rules: [rule(1)] }));
    await openEditor(user);
    await user.click(screen.getByRole("button", { name: "Remove dose 1" }));
    expect(screen.getByText("All dose timings will be removed when you save.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear dose timing" }));

    await waitFor(() => expect(updateMedication).toHaveBeenCalled());
    expect(updateMedication.mock.calls[0][1]).toEqual({ dose_rules: [] });
  });

  it("disables saving when nothing has changed", async () => {
    const user = userEvent.setup();
    renderList(med({ dose_rules: [rule(1)] }));
    await openEditor(user);
    expect(screen.getByRole("button", { name: "Save dose timing" })).toBeDisabled();
  });

  it("stops adding rules at the prescribed times per day", async () => {
    const user = userEvent.setup();
    renderList(med({ times_per_day: 1 }));
    await openEditor(user);
    const add = screen.getByRole("button", { name: "Add dose timing" });
    await user.click(add);
    expect(add).toBeDisabled();
    expect(screen.getByText("1 of 1 daily dose")).toBeInTheDocument();
  });

  it("warns when the chosen meal is missing from the routine, without inventing a time", async () => {
    const user = userEvent.setup();
    renderList(med());
    await openEditor(user);
    await user.click(screen.getByRole("button", { name: "Add dose timing" }));
    await user.selectOptions(screen.getByLabelText("When"), "lunch");
    expect(screen.getByText(/Lunch time isn't recorded in this patient's daily routine/)).toBeInTheDocument();
  });

  it("returns the saved medication and never generates a schedule", async () => {
    const user = userEvent.setup();
    const onUpdated = renderList(med({ dose_rules: [rule(1)] }));
    await openEditor(user);
    await user.selectOptions(screen.getByLabelText("Timing"), "after");
    await user.type(screen.getByLabelText("Minutes"), "15");
    await user.click(screen.getByRole("button", { name: "Save dose timing" }));

    await waitFor(() => expect(onUpdated).toHaveBeenCalledTimes(1));
    expect(generateMedicationSchedule).not.toHaveBeenCalled();
  });

  it("keeps the editor open and shows the server's reason if a save fails", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api/errors");
    updateMedication.mockRejectedValueOnce(new ApiError(422, "dose_rules sequences must be contiguous."));
    renderList(med({ dose_rules: [rule(1)] }));
    await openEditor(user);
    await user.selectOptions(screen.getByLabelText("Timing"), "after");
    await user.type(screen.getByLabelText("Minutes"), "15");
    await user.click(screen.getByRole("button", { name: "Save dose timing" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("dose_rules sequences must be contiguous.");
    expect(screen.getByRole("button", { name: "Save dose timing" })).toBeInTheDocument();
  });
});
