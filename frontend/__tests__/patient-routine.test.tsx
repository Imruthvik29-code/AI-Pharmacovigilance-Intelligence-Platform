import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PatientForm } from "@/components/PatientForm";
import { PatientRoutineForm } from "@/components/PatientRoutineForm";
import { ApiError } from "@/lib/api/errors";

const { createPatient, getPatient, updatePatient } = vi.hoisted(() => ({
  createPatient: vi.fn(),
  getPatient: vi.fn(),
  updatePatient: vi.fn(),
}));

vi.mock("@/lib/api/patients", () => ({ createPatient, getPatient, updatePatient }));

const patient = {
  id: "patient-1",
  user_id: "user-1",
  name: "Routine Person",
  relation: null,
  age: 40,
  sex: null,
  weight_kg: null,
  renal_flag: false,
  hepatic_flag: false,
  timezone: "Europe/London",
  breakfast_time: "07:30:00",
  lunch_time: null,
  dinner_time: "19:45:00",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

describe("PatientForm daily routine", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createPatient.mockResolvedValue({ ...patient, id: "new-patient" });
  });

  it("shows the routine fields labelled as context, not medication instructions", () => {
    render(<PatientForm onCreated={() => {}} />);

    expect(screen.getByRole("group", { name: /daily routine/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Timezone")).toBeInTheDocument();
    expect(screen.getByLabelText("Breakfast")).toBeInTheDocument();
    expect(screen.getByLabelText("Lunch")).toBeInTheDocument();
    expect(screen.getByLabelText("Dinner")).toBeInTheDocument();
    expect(screen.getByText(/not a medication instruction/i)).toBeInTheDocument();
  });

  it("prefills the detected timezone but lets the user replace it", async () => {
    const user = userEvent.setup();
    render(<PatientForm onCreated={() => {}} />);

    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const timezone = screen.getByLabelText("Timezone");
    expect(timezone).toHaveValue(detected);

    await user.clear(timezone);
    await user.type(timezone, "Asia/Kolkata");
    await user.type(screen.getByLabelText("Name"), "New Person");
    await user.click(screen.getByRole("button", { name: "Create patient" }));

    await waitFor(() => expect(createPatient).toHaveBeenCalled());
    expect(createPatient.mock.calls[0][0]).toMatchObject({ timezone: "Asia/Kolkata" });
  });

  it("submits null for meal times that were left blank", async () => {
    const user = userEvent.setup();
    render(<PatientForm onCreated={() => {}} />);

    await user.type(screen.getByLabelText("Name"), "Minimal Person");
    await user.click(screen.getByRole("button", { name: "Create patient" }));

    await waitFor(() => expect(createPatient).toHaveBeenCalled());
    expect(createPatient.mock.calls[0][0]).toMatchObject({
      breakfast_time: null,
      lunch_time: null,
      dinner_time: null,
    });
  });

  it("keeps the existing name/age/sex/relation behaviour intact", async () => {
    const user = userEvent.setup();
    render(<PatientForm onCreated={() => {}} />);

    const submit = screen.getByRole("button", { name: "Create patient" });
    expect(submit).toBeDisabled(); // still gated on name alone

    await user.type(screen.getByLabelText("Name"), "Jane");
    await user.type(screen.getByLabelText(/Age/), "62");
    await user.type(screen.getByLabelText(/Sex/), "female");
    expect(submit).toBeEnabled();

    await user.click(submit);
    await waitFor(() => expect(createPatient).toHaveBeenCalled());
    expect(createPatient.mock.calls[0][0]).toMatchObject({ name: "Jane", age: 62, sex: "female" });
  });
});

describe("PatientRoutineForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getPatient.mockResolvedValue(patient);
    updatePatient.mockResolvedValue({ ...patient, lunch_time: "12:15:00" });
  });

  it("loads the stored routine rather than the device timezone", async () => {
    render(<PatientRoutineForm patientId="patient-1" />);

    await waitFor(() => expect(screen.getByLabelText("Timezone")).toHaveValue("Europe/London"));
    expect(screen.getByLabelText("Breakfast")).toHaveValue("07:30");
    expect(screen.getByLabelText("Dinner")).toHaveValue("19:45");
    expect(screen.getByLabelText("Lunch")).toHaveValue("");
  });

  it("saves edited routine fields and reports success", async () => {
    const user = userEvent.setup();
    render(<PatientRoutineForm patientId="patient-1" />);

    await waitFor(() => expect(screen.getByLabelText("Lunch")).toBeInTheDocument());
    await user.type(screen.getByLabelText("Lunch"), "12:15");
    await user.click(screen.getByRole("button", { name: "Save routine" }));

    await waitFor(() => expect(updatePatient).toHaveBeenCalled());
    expect(updatePatient.mock.calls[0][0]).toBe("patient-1");
    expect(updatePatient.mock.calls[0][1]).toMatchObject({ lunch_time: "12:15" });
    expect(await screen.findByText("Daily routine saved.")).toBeInTheDocument();
  });

  it("sends only routine keys, never other patient fields", async () => {
    const user = userEvent.setup();
    render(<PatientRoutineForm patientId="patient-1" />);

    await waitFor(() => expect(screen.getByLabelText("Timezone")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Save routine" }));

    await waitFor(() => expect(updatePatient).toHaveBeenCalled());
    expect(Object.keys(updatePatient.mock.calls[0][1]).sort()).toEqual([
      "breakfast_time",
      "dinner_time",
      "lunch_time",
      "timezone",
    ]);
  });

  it("surfaces a load failure instead of an empty form", async () => {
    getPatient.mockRejectedValueOnce(new ApiError(503, "Could not load this patient."));
    render(<PatientRoutineForm patientId="patient-1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load this patient.");
    expect(screen.queryByLabelText("Timezone")).not.toBeInTheDocument();
  });

  it("surfaces a save failure and does not claim success", async () => {
    const user = userEvent.setup();
    updatePatient.mockRejectedValueOnce(new ApiError(422, "Invalid timezone."));
    render(<PatientRoutineForm patientId="patient-1" />);

    await waitFor(() => expect(screen.getByLabelText("Timezone")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Save routine" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid timezone.");
    expect(screen.queryByText("Daily routine saved.")).not.toBeInTheDocument();
  });
});
