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
    <section className="overflow-hidden rounded-2xl border border-line bg-card shadow-[0_1px_2px_rgba(20,32,41,0.04)]" aria-label="Patient timeline">
      <div className="border-b border-line px-5 py-4">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">Record</p>
        <h2 className="mt-1 text-base font-semibold tracking-tight">Timeline</h2>
        <p className="mt-1 text-xs leading-5 text-muted">A chronological view of recorded patient activity.</p>
      </div>
      <div className="px-5 pb-5">
        {loading ? (
          <div className="pt-4">
            <LoadingSkeleton label="Loading timeline" lines={3} />
          </div>
        ) : null}
        {error ? (
          <p className="pt-4 text-sm text-high" role="alert">
            {error}
          </p>
        ) : null}
        {!loading && !error && events.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-line bg-paper/60 px-4 py-5">
            <p className="text-sm font-medium">No events yet</p>
            <p className="mt-1 text-sm leading-6 text-muted">
              Adding a medication or running analysis will appear here.
            </p>
          </div>
        ) : null}
        {!loading && events.length > 0 ? (
          <ol className="relative mt-4 space-y-3 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-px before:bg-line">
            {events.map((event) => (
              <li key={event.id} className="relative pl-6">
                <span className="absolute left-0 top-4 h-2 w-2 rounded-full border-2 border-card bg-accent ring-1 ring-line" aria-hidden="true" />
                <div className={`rounded-xl border border-l-4 px-3.5 py-3 ${accentFor(event.event_type)}`}>
                  <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                    <p className="font-mono text-[10px] uppercase tracking-wide text-muted">
                      {labelFor(event.event_type)}
                    </p>
                    <time dateTime={event.event_time} className="text-[11px] text-muted">
                      {new Date(event.event_time).toLocaleString()}
                    </time>
                  </div>
                  <p className="mt-1 text-sm font-medium">{event.event_title}</p>
                  {event.event_description ? (
                    <p className="mt-1 text-sm leading-5 text-muted">{event.event_description}</p>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        ) : null}
      </div>
    </section>
  );
}
