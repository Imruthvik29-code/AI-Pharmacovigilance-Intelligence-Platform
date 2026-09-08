import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MedicationPicker } from "@/components/MedicationPicker";
import { searchReferenceDrugs } from "@/lib/api/referenceDrugs";

vi.mock("@/lib/api/referenceDrugs", () => ({
  searchReferenceDrugs: vi.fn(async () => [
    {
      id: "drug-1",
      name: "Examplecin",
      generic_name: null,
      rxcui: null,
      source: "FDA Label",
      term_type: null,
    },
    {
      id: "drug-2",
      name: "Exampleolol",
      generic_name: "Exampleolol",
      rxcui: null,
      source: "FDA Label",
      term_type: "IN",
    },
  ]),
}));

vi.mock("@/lib/api/medications", () => ({
  createMedication: vi.fn(),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

type CatalogDrug = {
  id: string;
  name: string;
  generic_name: string | null;
  rxcui: string | null;
  source: string | null;
  term_type: string | null;
};

describe("MedicationPicker keyboard", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.mocked(searchReferenceDrugs).mockImplementation(async () => [
      {
        id: "drug-1",
        name: "Examplecin",
        generic_name: null,
        rxcui: null,
        source: "FDA Label",
        term_type: null,
      },
      {
        id: "drug-2",
        name: "Exampleolol",
        generic_name: "Exampleolol",
        rxcui: null,
        source: "FDA Label",
        term_type: "IN",
      },
    ]);
  });

  it("moves the highlighted option and selects with Enter", async () => {
    const user = userEvent.setup();
    render(<MedicationPicker patientId="patient-1" onCreated={() => undefined} />);

    const input = screen.getByRole("combobox", { name: "Medicine name" });
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
    expect(screen.getByText("Medication selected")).toBeInTheDocument();
    expect(screen.getByText(/Exampleolol/)).toBeInTheDocument();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("closes the listbox on Escape without selecting", async () => {
    const user = userEvent.setup();
    render(<MedicationPicker patientId="patient-1" onCreated={() => undefined} />);

    const input = screen.getByRole("combobox", { name: "Medicine name" });
    await user.type(input, "ex");
    expect(await screen.findByRole("listbox")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/Selected/)).not.toBeInTheDocument();
  });

  it("ignores an older catalog response after the query changes", async () => {
    const first = deferred<CatalogDrug[]>();
    const second = deferred<CatalogDrug[]>();
    vi.mocked(searchReferenceDrugs).mockImplementation((query) =>
      query === "ex" ? first.promise : second.promise,
    );

    const user = userEvent.setup();
    render(<MedicationPicker patientId="patient-1" onCreated={() => undefined} />);
    const input = screen.getByRole("combobox", { name: "Medicine name" });

    await user.type(input, "ex");
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 350));
    });
    expect(searchReferenceDrugs).toHaveBeenCalledWith("ex");

    await user.type(input, "a");
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 350));
    });
    expect(searchReferenceDrugs).toHaveBeenCalledWith("exa");

    second.resolve([
      {
        id: "new-drug",
        name: "Newerdrug",
        generic_name: null,
        rxcui: null,
        source: "FDA Label",
        term_type: null,
      },
    ]);
    expect(await screen.findByRole("option", { name: /Newerdrug/i })).toBeInTheDocument();

    first.resolve([
      {
        id: "old-drug",
        name: "Olderdrug",
        generic_name: null,
        rxcui: null,
        source: "FDA Label",
        term_type: null,
      },
    ]);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByRole("option", { name: /Olderdrug/i })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Newerdrug/i })).toBeInTheDocument();
  });
});
