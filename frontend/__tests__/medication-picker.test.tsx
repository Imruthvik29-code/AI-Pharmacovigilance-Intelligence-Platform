import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MedicationPicker } from "@/components/MedicationPicker";

vi.mock("@/lib/api/referenceDrugs", () => ({
  searchReferenceDrugs: vi.fn(async () => [
    {
      id: "drug-1",
      name: "Examplecin",
      rxcui: null,
      source: "FDA Label",
      term_type: null,
    },
    {
      id: "drug-2",
      name: "Exampleolol",
      rxcui: null,
      source: "FDA Label",
      term_type: "IN",
    },
  ]),
}));

vi.mock("@/lib/api/medications", () => ({
  createMedication: vi.fn(),
}));

describe("MedicationPicker keyboard", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("moves the highlighted option and selects with Enter", async () => {
    const user = userEvent.setup();
    render(<MedicationPicker patientId="patient-1" onCreated={() => undefined} />);

    const input = screen.getByRole("combobox", { name: "Medication" });
    await user.type(input, "ex");

    const first = await screen.findByRole("option", { name: /Examplecin/i });
    expect(first).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByText("no TTY")).not.toBeInTheDocument();

    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: /Exampleolol/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    await user.keyboard("{Enter}");
    expect(screen.getByText(/Selected/)).toHaveTextContent("Exampleolol");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("closes the listbox on Escape without selecting", async () => {
    const user = userEvent.setup();
    render(<MedicationPicker patientId="patient-1" onCreated={() => undefined} />);

    const input = screen.getByRole("combobox", { name: "Medication" });
    await user.type(input, "ex");
    expect(await screen.findByRole("listbox")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/Selected/)).not.toBeInTheDocument();
  });
});
