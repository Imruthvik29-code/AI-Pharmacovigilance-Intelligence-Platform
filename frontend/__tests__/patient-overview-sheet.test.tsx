import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PatientOverviewSheet } from "@/components/PatientOverviewSheet";

describe("PatientOverviewSheet", () => {
  it("presents Overview as the raised current item and routes each product section to its details", () => {
    const onViewDetails = vi.fn();
    render(<PatientOverviewSheet analysis={null} medications={[]} symptoms={[]} timeline={[]} onViewDetails={onViewDetails} onRunAnalysis={vi.fn()} analysisRunning={false} />);

    expect(screen.getByRole("region", { name: "Patient overview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Overview" })).toHaveClass("is-active");
    fireEvent.click(screen.getByRole("button", { name: "Medications" }));
    expect(onViewDetails).toHaveBeenCalledWith("medications");
    expect(screen.getByRole("region", { name: "Patient workspace" })).toBeInTheDocument();
  });
});
