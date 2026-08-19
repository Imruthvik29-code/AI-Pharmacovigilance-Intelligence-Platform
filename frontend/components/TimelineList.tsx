import type { TimelineEventResponse } from "@/lib/api/types";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";

function labelFor(eventType: string): string {
  return eventType.replaceAll("_", " ");
}

function accentFor(eventType: string): string {
  if (eventType === "analysis_run") return "border-accent bg-[#eef6f4]";
  if (eventType === "medication_started" || eventType === "medication_discontinued") {
    return "border-ink/40 bg-card";
  }
  return "border-line bg-card";
}

export function TimelineList({
  events,
  loading,
  error,
}: {
  events: TimelineEventResponse[];
  loading?: boolean;
  error?: string | null;
}) {
  return (
    <section className="rounded-2xl border border-line bg-card p-5" aria-label="Patient timeline">
      <h2 className="text-sm font-semibold">Timeline</h2>
      <p className="mt-1 text-xs text-muted">Automatically recorded as you add medications and run analysis.</p>
      {loading ? (
        <div className="mt-4">
          <LoadingSkeleton label="Loading timeline" lines={3} />
        </div>
      ) : null}
      {error ? (
        <p className="mt-4 text-sm text-high" role="alert">
          {error}
        </p>
      ) : null}
      {!loading && !error && events.length === 0 ? (
        <p className="mt-4 text-sm text-muted">No events yet. Adding a medication or running analysis will appear here.</p>
      ) : null}
      {!loading && events.length > 0 ? (
        <ol className="mt-4 space-y-2.5">
          {events.map((event) => (
            <li
              key={event.id}
              className={`rounded-lg border-l-4 px-3 py-2.5 ${accentFor(event.event_type)}`}
            >
              <p className="font-mono text-[11px] uppercase tracking-wide text-muted">
                {labelFor(event.event_type)} · {new Date(event.event_time).toLocaleString()}
              </p>
              <p className="mt-0.5 text-sm font-medium">{event.event_title}</p>
              {event.event_description ? (
                <p className="text-sm text-muted">{event.event_description}</p>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
