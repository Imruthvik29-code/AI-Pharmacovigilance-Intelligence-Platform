import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SymptomPanel, newestOnsetFirst } from "@/components/SymptomPanel";
import { createSymptom } from "@/lib/api/symptoms";
import { ApiError } from "@/lib/api/errors";
import type { MedicationResponse, SymptomResponse } from "@/lib/api/types";

vi.mock("@/lib/api/symptoms", () => ({ createSymptom: vi.fn() }));

const medication = {
  id: "med-1", patient_id: "patient-1", drug_id: "drug-1", drug_name: "Ibuprofen 400 mg oral tablet",
  drug_generic_name: "ibuprofen", drug_term_type: "SCD", drug_source: "RxNorm", condition_id: null,
  purpose_text: null, dose: "1 tablet", times_per_day: 2, interval_hours: null, duration_days: 5,
  start_date: "2026-09-01", end_date: null, status: "active",
  created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-01T10:00:00Z",
} satisfies MedicationResponse;

function symptom(overrides: Partial<SymptomResponse>): SymptomResponse {
  return {
    id: "s", patient_id: "patient-1", condition_id: null, medication_id: null,
    description: "Headache", severity: "mild", onset_date: "2026-09-10", resolved_date: null,
    created_at: "2026-09-10T08:00:00Z", updated_at: "2026-09-10T08:00:00Z", ...overrides,
  };
}

// API order: onset ascending, then recorded time ascending.
const symptoms = [
  symptom({ id: "s-old", description: "Dry cough", severity: "moderate", onset_date: "2026-09-02", resolved_date: "2026-09-06" }),
  symptom({ id: "s-new", description: "Stomach pain after meals", severity: "severe", onset_date: "2026-09-12", medication_id: "med-1" }),
];

function renderPanel(props: Partial<React.ComponentProps<typeof SymptomPanel>> = {}) {
  const onCreated = vi.fn();
  const onRetry = vi.fn();
  render(
    <SymptomPanel
      patientId="patient-1"
      medications={[medication]}
      symptoms={symptoms}
      onCreated={onCreated}
      onRetry={onRetry}
      {...props}
    />,
  );
  return { onCreated, onRetry };
}

describe("Symptoms detail panel", () => {
  beforeEach(() => vi.resetAllMocks());

  it("lists recorded symptoms newest onset first with their recorded details", () => {
    renderPanel();

    const names = screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent);
    expect(names).toEqual(["Stomach pain after meals", "Dry cough"]);
    expect(screen.getByText("1 unresolved of 2 reported")).toBeInTheDocument();

    const [recent, older] = screen.getAllByRole("article");
    expect(within(recent).getByText("severe")).toBeInTheDocument();
    expect(within(recent).getByText("Ongoing")).toBeInTheDocument();
    expect(within(recent).getByText("Related medication")).toBeInTheDocument();
    expect(within(recent).getByText("Ibuprofen 400 mg oral tablet")).toBeInTheDocument();
    expect(within(recent).queryByText("Resolved")).not.toBeInTheDocument();

    expect(within(older).getByText("moderate")).toBeInTheDocument();
    expect(within(older).getAllByText("Resolved")).toHaveLength(2); // status tag + resolved date label
    expect(within(older).queryByText("Related medication")).not.toBeInTheDocument();
  });

  it("names a linked medication only from recorded data", () => {
    renderPanel({ symptoms: [symptom({ id: "s1", medication_id: "med-missing" })] });
    expect(screen.getByText("Name not available")).toBeInTheDocument();
    expect(screen.queryByText("med-missing")).not.toBeInTheDocument();
  });

  it("orders by onset, then by when the symptom was recorded", () => {
    const sameDay = [
      symptom({ id: "a", onset_date: "2026-09-05", created_at: "2026-09-05T08:00:00Z" }),
      symptom({ id: "b", onset_date: "2026-09-05", created_at: "2026-09-05T09:00:00Z" }),
      symptom({ id: "c", onset_date: "2026-09-01", created_at: "2026-09-20T09:00:00Z" }),
    ];
    expect(newestOnsetFirst(sameDay).map((item) => item.id)).toEqual(["b", "a", "c"]);
  });

  it("shows loading without a premature empty state", () => {
    renderPanel({ symptoms: [], loading: true });
    expect(screen.getByRole("status", { name: "Loading symptoms" })).toBeInTheDocument();
    expect(screen.queryByText("No symptoms recorded")).not.toBeInTheDocument();
  });

  it("shows a failed load as an error with a retry, never as empty", () => {
    const { onRetry } = renderPanel({ symptoms: [], error: "Could not load symptoms." });
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load symptoms.");
    expect(screen.queryByText("No symptoms recorded")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows the empty state when the patient has no symptoms", () => {
    renderPanel({ symptoms: [] });
    expect(screen.getByText("No symptoms recorded")).toBeInTheDocument();
    expect(screen.queryByText(/unresolved of/)).not.toBeInTheDocument();
  });

  it("reports a symptom for this patient and closes the form", async () => {
    const created = symptom({ id: "s-created", description: "Dizziness" });
    vi.mocked(createSymptom).mockResolvedValue(created);
    const { onCreated } = renderPanel();

    const trigger = screen.getByRole("button", { name: /Report a symptom/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    fireEvent.change(screen.getByLabelText("What are you experiencing?"), { target: { value: "  Dizziness  " } });
    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "moderate" } });
    fireEvent.change(screen.getByLabelText("Onset date"), { target: { value: "2026-09-14" } });
    fireEvent.change(screen.getByLabelText(/Related medication/), { target: { value: "med-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Report symptom" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created));
    expect(createSymptom).toHaveBeenCalledWith("patient-1", {
      description: "Dizziness",
      severity: "moderate",
      onset_date: "2026-09-14",
      medication_id: "med-1",
    });
    expect(screen.queryByLabelText("What are you experiencing?")).not.toBeInTheDocument();
  });

  it("keeps the form open and shows the API message when reporting fails", async () => {
    vi.mocked(createSymptom).mockRejectedValue(new ApiError(400, "Medication does not belong to this patient."));
    const { onCreated } = renderPanel();

    fireEvent.click(screen.getByRole("button", { name: /Report a symptom/ }));
    fireEvent.change(screen.getByLabelText("What are you experiencing?"), { target: { value: "Rash" } });
    fireEvent.click(screen.getByRole("button", { name: "Report symptom" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Medication does not belong to this patient.");
    expect(onCreated).not.toHaveBeenCalled();
    expect(screen.getByLabelText("What are you experiencing?")).toHaveValue("Rash");
  });
});
