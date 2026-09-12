import { IconChip } from "@/components/ui/IconChip";
import { AlertIcon, CalendarIcon, CapsuleIcon, PulseIcon, SparkIcon } from "@/components/icons/Icons";
import { formatDateTime } from "@/lib/patient/summaries";
import type { TimelineEventResponse } from "@/lib/api/types";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";

function labelFor(eventType: string): string {
  return eventType.replaceAll("_", " ");
}

/** Event-type tint. Restrained: the four clinical tints, nothing new. */
function toneFor(eventType: string) {
  if (eventType === "analysis_run") return { Icon: SparkIcon, surface: "var(--safety-surface)", ink: "var(--safety-ink)" };
  if (eventType.startsWith("medication")) {
    return { Icon: CapsuleIcon, surface: "var(--medications-surface)", ink: "var(--medications-ink)" };
  }
  if (eventType.startsWith("dose")) {
    return { Icon: CapsuleIcon, surface: "var(--medications-surface)", ink: "var(--medications-ink)" };
  }
  if (eventType.startsWith("symptom")) {
    return { Icon: PulseIcon, surface: "var(--symptoms-surface)", ink: "var(--symptoms-ink)" };
  }
  if (eventType.startsWith("condition")) {
    return { Icon: AlertIcon, surface: "var(--timeline-surface)", ink: "var(--timeline-ink)" };
  }
  return { Icon: CalendarIcon, surface: "var(--timeline-surface)", ink: "var(--timeline-ink)" };
}

export function TimelineList({
  events,
  loading,
  error,
  showHeading = true,
}: {
  events: TimelineEventResponse[];
  loading?: boolean;
  error?: string | null;
  /** Off when the surrounding DetailSheet already names the section. */
  showHeading?: boolean;
}) {
  return (
    <section aria-label="Patient timeline">
      {showHeading ? (
        <div className="px-1">
          <p className="pv-eyebrow">
            Record
          </p>
          <h2 className="pv-section-title mt-0.5">Timeline</h2>
          <p className="mt-1 text-[0.8125rem] leading-5 text-ink-2">
            A chronological view of recorded patient activity.
          </p>
        </div>
      ) : null}

      <div className={`${showHeading ? "mt-3" : ""} space-y-2`}>
        {loading ? <LoadingSkeleton label="Loading timeline" lines={3} /> : null}
        {error ? (
          <p className="rounded-row bg-severe-bg px-4 py-3 text-[0.875rem] text-severe" role="alert">
            {error}
          </p>
        ) : null}
        {!loading && !error && events.length === 0 ? (
          <div className="rounded-row bg-surface-2 px-4 py-5">
            <p className="text-[0.9375rem] font-semibold">No events yet</p>
            <p className="mt-1 text-[0.875rem] leading-6 text-ink-2">
              Adding a medication or running analysis will appear here.
            </p>
          </div>
        ) : null}

        {!loading && events.length > 0 ? (
          <ol className="space-y-2">
            {events.map((event) => {
              const tone = toneFor(event.event_type);
              return (
                <li key={event.id} className="pv-row items-start">
                  <IconChip Icon={tone.Icon} surface={tone.surface} ink={tone.ink} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                      <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.1em] text-ink-3">
                        {labelFor(event.event_type)}
                      </p>
                      <time dateTime={event.event_time} className="text-[0.75rem] text-ink-3">
                        {formatDateTime(event.event_time)}
                      </time>
                    </div>
                    <p className="mt-1 text-[0.9375rem] font-medium tracking-[-0.01em]">
                      {event.event_title}
                    </p>
                    {event.event_description ? (
                      <p className="mt-0.5 text-[0.8125rem] leading-5 text-ink-2">
                        {event.event_description}
                      </p>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>
        ) : null}
      </div>
    </section>
  );
}
