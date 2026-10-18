import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TimelineList } from "@/components/TimelineList";
import type { TimelineEventResponse } from "@/lib/api/types";

const local = (day: number, hour: number, minute = 0) => new Date(2026, 8, day, hour, minute).toISOString();

// API order: most recent first.
const events: TimelineEventResponse[] = [
  { id: "e3", patient_id: "p1", event_type: "symptom_reported", ref_id: "s1", event_title: "Symptom reported: Dizziness when standing up",
    event_description: null, event_time: local(14, 18, 30), payload: { severity: "moderate", medication_id: null }, created_at: local(14, 18, 30) },
  { id: "e2", patient_id: "p1", event_type: "dose_missed", ref_id: "d1", event_title: "Missed dose of Ibuprofen",
    event_description: null, event_time: local(14, 9), payload: { scheduled_time: local(14, 8), auto_detected: true }, created_at: local(14, 9) },
  { id: "e1", patient_id: "p1", event_type: "medication_started", ref_id: "m1", event_title: "Started Ibuprofen 400 MG Oral Tablet",
    event_description: "1 tablet", event_time: local(12, 10), payload: { dose: "1 tablet" }, created_at: local(12, 10) },
];

describe("Timeline detail list", () => {
  it("renders recorded events under their local day, in API order", () => {
    render(<TimelineList events={events} />);

    expect(screen.getByText("3 events")).toBeInTheDocument();
    const days = screen.getAllByRole("heading", { level: 3 });
    expect(days).toHaveLength(2);

    const items = screen.getAllByRole("listitem");
    expect(items.map((item) => within(item).getByText(/Symptom reported:|Missed dose|Started/).textContent)).toEqual([
      "Symptom reported: Dizziness when standing up",
      "Missed dose of Ibuprofen",
      "Started Ibuprofen 400 MG Oral Tablet",
    ]);

    expect(within(items[0]).getByText("Symptom reported")).toBeInTheDocument();
    expect(within(items[0]).getByText("moderate")).toBeInTheDocument();
    expect(within(items[1]).getByText("Dose missed")).toBeInTheDocument();
    expect(within(items[1]).getByText("Marked automatically once overdue")).toBeInTheDocument();
    expect(within(items[2]).getByText("1 tablet")).toBeInTheDocument();
    expect(within(items[2]).getByText("Medication started")).toBeInTheDocument();
    expect(items[2].querySelector("time")).toHaveAttribute("dateTime", events[2].event_time);
  });

  it("shows loading without a premature empty state", () => {
    render(<TimelineList events={[]} loading />);
    expect(screen.getByRole("status", { name: "Loading timeline" })).toBeInTheDocument();
    expect(screen.queryByText("No events recorded yet")).not.toBeInTheDocument();
  });

  it("shows a failed load as an error with a retry, never as empty", () => {
    const onRetry = vi.fn();
    render(<TimelineList events={[]} error="Could not load timeline." onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load timeline.");
    expect(screen.queryByText("No events recorded yet")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows the empty state only for a successful empty response", () => {
    render(<TimelineList events={[]} />);
    expect(screen.getByText("No events recorded yet")).toBeInTheDocument();
    expect(screen.queryByText(/^\d+ events?$/)).not.toBeInTheDocument();
  });
});
