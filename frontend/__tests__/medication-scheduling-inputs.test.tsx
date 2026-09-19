import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MedicationPicker } from "@/components/MedicationPicker";
import { SchedulePanel } from "@/components/SchedulePanel";
import { createMedication } from "@/lib/api/medications";
import { generateMedicationSchedule } from "@/lib/api/schedule";
import type { MedicationResponse } from "@/lib/api/types";
import { localCalendarDate } from "@/lib/dates/localDate";

vi.mock("@/lib/api/referenceDrugs", () => ({
  searchReferenceDrugs: vi.fn(async () => [
    { id: "drug-1", name: "Examplecin", generic_name: null, rxcui: null, source: "FDA Label", term_type: null },
  ]),
}));
vi.mock("@/lib/api/medications", () => ({ createMedication: vi.fn() }));
vi.mock("@/lib/api/schedule", () => ({
  generateMedicationSchedule: vi.fn(async () => []),
  listUpcomingDoses: vi.fn(async () => []),
  markDose: vi.fn(),
}));

const medication: MedicationResponse = {
  id: "medication-1", patient_id: "patient-1", drug_id: "drug-1", condition_id: null,
  purpose_text: null, dose: null, times_per_day: null, interval_hours: null, duration_days: null,
  start_date: "2026-09-19", end_date: null, status: "active",
  created_at: "2026-09-19T10:00:00Z", updated_at: "2026-09-19T10:00:00Z",
  drug_name: "Examplecin", drug_generic_name: null, drug_term_type: null, drug_source: "FDA Label",
};

async function selectDrug(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole("combobox", { name: "Medicine name" }), "ex");
  await user.click(await screen.findByRole("option", { name: /Examplecin/ }));
}

async function fillSchedule(user: ReturnType<typeof userEvent.setup>, mode = "times_per_day", value = "2") {
  await user.type(screen.getByLabelText("Duration (days)"), "7");
  await user.selectOptions(screen.getByLabelText("Frequency mode"), mode);
  await user.type(screen.getByLabelText(mode === "times_per_day" ? "Times per day" : "Hours between doses"), value);
}

function CreationAndSchedule() {
  const [medications, setMedications] = useState<MedicationResponse[]>([]);
  return <>
    <MedicationPicker patientId="patient-1" onCreated={(created) => setMedications((items) => [...items, created])} />
    <SchedulePanel patientId="patient-1" medications={medications} />
  </>;
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  vi.mocked(createMedication).mockImplementation(async (_patientId, payload) => ({ ...medication, ...payload }));
});

describe("medication scheduling inputs", () => {
  it("starts without prescription defaults and keeps creation unavailable", () => {
    render(<MedicationPicker patientId="patient-1" onCreated={vi.fn()} />);
    expect(screen.getByLabelText("Duration (days)")).toHaveValue(null);
    expect(screen.getByLabelText("Frequency mode")).toHaveValue("");
    expect(screen.getByLabelText("Frequency value")).toHaveValue(null);
    expect(screen.getByLabelText("Frequency value")).toBeDisabled();
    expect(screen.getByLabelText("Start date")).toHaveValue(localCalendarDate());
    expect(screen.getByRole("button", { name: "Add medication" })).toBeDisabled();
  });

  it.each([
    ["times_per_day", "2", { times_per_day: 2, interval_hours: null }],
    ["interval_hours", "6.5", { times_per_day: null, interval_hours: 6.5 }],
  ])("saves the exact %s payload and preserves existing prescription fields", async (mode, value, frequency) => {
    const user = userEvent.setup();
    const onCreated = vi.fn();
    render(<MedicationPicker patientId="patient-1" onCreated={onCreated} />);
    await selectDrug(user);
    await fillSchedule(user, mode, value);
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-10-02" } });
    await user.type(screen.getByLabelText(/Dose/), " 1 tablet ");
    await user.type(screen.getByLabelText(/Purpose/), " Migraine ");
    await user.click(screen.getByRole("button", { name: "Add medication" }));
    const payload = { drug_id: "drug-1", start_date: "2026-10-02", status: "active", dose: "1 tablet", purpose_text: "Migraine", duration_days: 7, ...frequency };
    expect(createMedication).toHaveBeenCalledExactlyOnceWith("patient-1", payload);
    await waitFor(() => expect(onCreated).toHaveBeenCalledExactlyOnceWith({ ...medication, ...payload }));
    expect(generateMedicationSchedule).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Duration (days)")).toHaveValue(null);
    expect(screen.getByLabelText("Frequency mode")).toHaveValue("");
  });

  it.each(["", "0", "-1", "1.5", "1e309", "9007199254740992"])("rejects missing or invalid duration %s even on direct submission", async (value) => {
    const user = userEvent.setup();
    const { container } = render(<MedicationPicker patientId="patient-1" onCreated={vi.fn()} />);
    await selectDrug(user);
    await fillSchedule(user);
    fireEvent.change(screen.getByLabelText("Duration (days)"), { target: { value } });
    fireEvent.blur(screen.getByLabelText("Duration (days)"));
    expect(screen.getByLabelText("Duration (days)")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Duration (days)")).toHaveAccessibleDescription("Enter a whole number of days, at least 1.");
    expect(screen.getByRole("button", { name: "Add medication" })).toBeDisabled();
    fireEvent.submit(container.querySelector("form")!);
    expect(createMedication).not.toHaveBeenCalled();
  });

  it.each([
    ["times_per_day", ""], ["times_per_day", "0"], ["times_per_day", "-2"],
    ["times_per_day", "25"], ["times_per_day", "1.5"],
    ["interval_hours", ""], ["interval_hours", "0"], ["interval_hours", "-0.5"], ["interval_hours", "1e309"],
  ])("rejects invalid %s value %s even on direct submission", async (mode, value) => {
    const user = userEvent.setup();
    const { container } = render(<MedicationPicker patientId="patient-1" onCreated={vi.fn()} />);
    await selectDrug(user);
    await fillSchedule(user, mode);
    const input = screen.getByLabelText(mode === "times_per_day" ? "Times per day" : "Hours between doses");
    fireEvent.change(input, { target: { value } });
    fireEvent.blur(input);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Add medication" })).toBeDisabled();
    fireEvent.submit(container.querySelector("form")!);
    expect(createMedication).not.toHaveBeenCalled();
  });

  it.each([
    ["times_per_day", "interval_hours", "0.5", { times_per_day: null, interval_hours: 0.5 }],
    ["interval_hours", "times_per_day", "24", { times_per_day: 24, interval_hours: null }],
  ])("clears the old %s value when switching to %s and submits only the chosen mode", async (from, to, value, frequency) => {
    const user = userEvent.setup();
    render(<MedicationPicker patientId="patient-1" onCreated={vi.fn()} />);
    await selectDrug(user);
    await fillSchedule(user, from);
    await user.selectOptions(screen.getByLabelText("Frequency mode"), to);
    const input = screen.getByLabelText(to === "times_per_day" ? "Times per day" : "Hours between doses");
    expect(input).toHaveValue(null);
    expect(screen.getByRole("button", { name: "Add medication" })).toBeDisabled();
    await user.type(input, value);
    await user.click(screen.getByRole("button", { name: "Add medication" }));
    expect(createMedication).toHaveBeenCalledExactlyOnceWith("patient-1", {
      drug_id: "drug-1", start_date: localCalendarDate(), status: "active", dose: null,
      purpose_text: null, duration_days: 7, ...frequency,
    });
  });

  it.each(["times_per_day", "interval_hours"])("makes a new %s medication schedulable but waits for the explicit action", async (mode) => {
    const user = userEvent.setup();
    render(<CreationAndSchedule />);
    expect(screen.queryByRole("button", { name: "Create schedule for Examplecin" })).not.toBeInTheDocument();
    await selectDrug(user);
    await fillSchedule(user, mode);
    await user.click(screen.getByRole("button", { name: "Add medication" }));
    const createSchedule = await screen.findByRole("button", { name: "Create schedule for Examplecin" });
    expect(generateMedicationSchedule).not.toHaveBeenCalled();
    await user.click(createSchedule);
    expect(generateMedicationSchedule).toHaveBeenCalledExactlyOnceWith("medication-1");
    expect(await screen.findByText("Schedule generated. Upcoming doses are now shown below.")).toBeInTheDocument();
  });
});
