import { describe, expect, it } from "vitest";
import { eventCategory, eventFacts, eventTypeLabel, groupByLocalDay } from "@/lib/timeline/events";
import type { TimelineEventResponse } from "@/lib/api/types";

/** An ISO instant for a LOCAL wall-clock time, so grouping is timezone-proof. */
const local = (day: number, hour: number, minute = 0) => new Date(2026, 8, day, hour, minute).toISOString();

function event(overrides: Partial<TimelineEventResponse>): TimelineEventResponse {
  return {
    id: "e", patient_id: "p1", event_type: "medication_started", ref_id: null, event_title: "Started Ibuprofen",
    event_description: null, event_time: local(12, 9), payload: null, created_at: local(12, 9), ...overrides,
  };
}

describe("timeline event helpers", () => {
  it("labels every event type the backend writes, and unknown types as recorded", () => {
    expect(eventTypeLabel("dose_missed")).toBe("Dose missed");
    expect(eventTypeLabel("condition_status_changed")).toBe("Condition status changed");
    expect(eventTypeLabel("analysis_run")).toBe("Safety analysis run");
    expect(eventTypeLabel("lab_result_added")).toBe("Lab result added");
  });

  it("assigns events to their clinical area by recorded type", () => {
    expect(eventCategory("analysis_run")).toBe("safety");
    expect(eventCategory("dose_taken")).toBe("medications");
    expect(eventCategory("medication_discontinued")).toBe("medications");
    expect(eventCategory("symptom_reported")).toBe("symptoms");
    expect(eventCategory("condition_status_changed")).toBe("timeline");
  });

  it("groups consecutive same-day events without reordering anything", () => {
    const events = [
      event({ id: "a", event_time: local(14, 18) }),
      event({ id: "b", event_time: local(14, 8) }),
      event({ id: "c", event_time: local(12, 21) }),
    ];
    const days = groupByLocalDay(events);
    expect(days.map((day) => day.events.map((item) => item.id))).toEqual([["a", "b"], ["c"]]);
    expect(days[0].dateTime).toBe("2026-09-14");
    expect(days.flatMap((day) => day.events)).toEqual(events);
  });

  it("reads dose facts only from the recorded payload", () => {
    const missed = eventFacts(event({
      event_type: "dose_missed",
      payload: { scheduled_time: local(12, 8), auto_detected: true, medication_id: "m1" },
    }));
    expect(missed.notes[0]).toMatch(/^Scheduled /);
    expect(missed.notes).toContain("Marked automatically once overdue");

    const marked = eventFacts(event({ event_type: "dose_missed", payload: { scheduled_time: local(12, 8) } }));
    expect(marked.notes).not.toContain("Marked automatically once overdue");

    expect(eventFacts(event({ event_type: "dose_taken", payload: { scheduled_time: "not a date" } })).notes).toEqual([]);
    expect(eventFacts(event({ event_type: "dose_taken", payload: null })).notes).toEqual([]);
  });

  it("shows a symptom's severity only when the payload records a valid one", () => {
    expect(eventFacts(event({ event_type: "symptom_reported", payload: { severity: "severe" } })).severity).toBe("severe");
    expect(eventFacts(event({ event_type: "symptom_reported", payload: { severity: "extreme" } })).severity).toBeNull();
    expect(eventFacts(event({ event_type: "analysis_run", payload: { severity: "severe" } })).severity).toBeNull();
  });
});
