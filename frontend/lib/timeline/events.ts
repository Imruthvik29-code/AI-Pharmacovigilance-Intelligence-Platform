import type { SeverityLevel, TimelineEventResponse } from "@/lib/api/types";

/**
 * Read-only presentation helpers for recorded timeline events. Nothing here
 * creates, infers or reorders an event: labels come from the recorded
 * event_type, days from the recorded event_time (shown in the viewer's local
 * time, as the rest of the app does), and facts only from payload fields the
 * backend writes for that event type.
 */

/** Labels for the event types the backend writes today. */
const EVENT_TYPE_LABELS: Record<string, string> = {
  medication_started: "Medication started",
  medication_discontinued: "Medication discontinued",
  dose_taken: "Dose taken",
  dose_missed: "Dose missed",
  dose_skipped: "Dose skipped",
  symptom_reported: "Symptom reported",
  condition_status_changed: "Condition status changed",
  analysis_run: "Safety analysis run",
};

/** A readable label; an unknown type is shown as recorded, just unsnaked. */
export function eventTypeLabel(eventType: string): string {
  const known = EVENT_TYPE_LABELS[eventType];
  if (known) return known;
  const words = eventType.replaceAll("_", " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : "Recorded event";
}

export type EventCategory = "safety" | "medications" | "symptoms" | "timeline";

/** Which clinical area an event belongs to, by its recorded type. */
export function eventCategory(eventType: string): EventCategory {
  if (eventType === "analysis_run") return "safety";
  if (eventType.startsWith("medication") || eventType.startsWith("dose")) return "medications";
  if (eventType.startsWith("symptom")) return "symptoms";
  return "timeline";
}

function localDayKey(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return `raw:${value}`;
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}

export type EventDay = { key: string; label: string; dateTime: string | null; events: TimelineEventResponse[] };

/**
 * Consecutive events that fall on the same local day, in the order the API
 * returned them (most recent first). Grouping never moves an event.
 */
export function groupByLocalDay(events: TimelineEventResponse[]): EventDay[] {
  const days: EventDay[] = [];
  for (const event of events) {
    const key = localDayKey(event.event_time);
    const last = days[days.length - 1];
    if (last && last.key === key) {
      last.events.push(event);
      continue;
    }
    const date = new Date(event.event_time);
    const valid = !Number.isNaN(date.getTime());
    days.push({
      key,
      label: valid
        ? date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" })
        : "Date not available",
      dateTime: valid ? localDayKey(event.event_time).split("-").map((part) => part.padStart(2, "0")).join("-") : null,
      events: [event],
    });
  }
  return days;
}

/** The recorded time of day, in the viewer's local time. */
export function formatEventTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function formatScheduled(value: string): string | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

export type EventFacts = { severity: SeverityLevel | null; notes: string[] };

const SEVERITIES: readonly SeverityLevel[] = ["mild", "moderate", "severe"];

/**
 * Facts the backend records in the payload for specific event types. Anything
 * missing or malformed is simply not shown.
 */
export function eventFacts(event: TimelineEventResponse): EventFacts {
  const payload = event.payload ?? {};
  const notes: string[] = [];
  let severity: SeverityLevel | null = null;

  if (event.event_type.startsWith("dose_")) {
    const scheduled = typeof payload.scheduled_time === "string" ? formatScheduled(payload.scheduled_time) : null;
    if (scheduled) notes.push(`Scheduled ${scheduled}`);
    if (event.event_type === "dose_missed" && payload.auto_detected === true) {
      notes.push("Marked automatically once overdue");
    }
  }

  if (event.event_type === "symptom_reported" && SEVERITIES.includes(payload.severity as SeverityLevel)) {
    severity = payload.severity as SeverityLevel;
  }

  return { severity, notes };
}
