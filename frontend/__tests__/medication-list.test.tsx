import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { MedicationList } from "@/components/MedicationList";
import { UNCACHED_DRUG_LABEL, rememberDrug } from "@/lib/drugs/nameCache";
import type { MedicationResponse } from "@/lib/api/types";

const medication: MedicationResponse = {
  id: "med-1",
  patient_id: "patient-1",
  condition_id: null,
  purpose_text: null,
  drug_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  dose: "5 mg",
  times_per_day: null,
  interval_hours: null,
  duration_days: null,
  status: "active",
  start_date: "2026-08-19",
  end_date: null,
  created_at: "2026-08-19T12:00:00Z",
  updated_at: "2026-08-19T12:00:00Z",
  drug_name: null,
  drug_generic_name: null,
  drug_term_type: null,
  drug_source: null,
};

describe("MedicationList", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("does not render a raw UUID when the name is not cached", () => {
    render(<MedicationList medications={[medication]} />);
    expect(screen.getByText(UNCACHED_DRUG_LABEL)).toBeInTheDocument();
    expect(screen.queryByText(medication.drug_id)).not.toBeInTheDocument();
    expect(screen.queryByText(/drug_id/i)).not.toBeInTheDocument();
  });

  it("renders a cached catalog name", () => {
    rememberDrug({
      id: medication.drug_id,
      name: "Examplecin",
      generic_name: null,
      rxcui: null,
      source: null,
      term_type: null,
    });
    render(<MedicationList medications={[medication]} />);
    expect(screen.getByText("Examplecin")).toBeInTheDocument();
    expect(screen.queryByText("no TTY")).not.toBeInTheDocument();
  });

  it("prefers the server catalog identity over the browser cache", () => {
    rememberDrug({
      id: medication.drug_id,
      name: "Stale browser name",
      generic_name: null,
      rxcui: null,
      source: "RxNorm",
      term_type: "IN",
    });
    render(
      <MedicationList
        medications={[
          {
            ...medication,
            drug_name: "Verified Tablet",
            drug_generic_name: "Example ingredient",
            drug_term_type: "SBD",
            drug_source: "CDCI",
          },
        ]}
      />,
    );
    expect(screen.getByText("Verified Tablet")).toBeInTheDocument();
    expect(screen.getByText(/Branded medication · Example ingredient · 5 mg/)).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.queryByText("Stale browser name")).not.toBeInTheDocument();
  });

  it("omits its repeated heading when embedded in the medication detail", () => {
    render(<MedicationList medications={[medication]} embedded />);

    expect(screen.getByLabelText("Medication list")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Medications" })).not.toBeInTheDocument();
    expect(screen.queryByText("Treatment")).not.toBeInTheDocument();
    expect(screen.queryByText("Current medication record.")).not.toBeInTheDocument();
    expect(screen.getByText(UNCACHED_DRUG_LABEL)).toBeInTheDocument();
  });
});
