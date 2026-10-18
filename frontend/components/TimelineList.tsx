"use client";

import { useId } from "react";
import { IconChip } from "@/components/ui/IconChip";
import { SeverityPill } from "@/components/ui/SeverityPill";
import { AlertIcon, CalendarIcon, CapsuleIcon, PulseIcon, SparkIcon } from "@/components/icons/Icons";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import type { TimelineEventResponse } from "@/lib/api/types";
import {
  eventCategory,
  eventFacts,
  eventTypeLabel,
  formatEventTime,
  groupByLocalDay,
} from "@/lib/timeline/events";

/** Event-type tint: the four clinical category tokens, nothing new. */
function toneFor(eventType: string) {
  const category = eventCategory(eventType);
  if (category === "safety") return { Icon: SparkIcon, surface: "var(--safety-bg)", ink: "var(--safety-fg)" };
  if (category === "medications") return { Icon: CapsuleIcon, surface: "var(--medications-bg)", ink: "var(--medications-fg)" };
  if (category === "symptoms") return { Icon: PulseIcon, surface: "var(--symptoms-bg)", ink: "var(--symptoms-fg)" };
  if (eventType.startsWith("condition")) return { Icon: AlertIcon, surface: "var(--timeline-bg)", ink: "var(--timeline-fg)" };
  return { Icon: CalendarIcon, surface: "var(--timeline-bg)", ink: "var(--timeline-fg)" };
}

export function TimelineList({
  events,
  loading,
  error,
  onRetry,
}: {
  events: TimelineEventResponse[];
  loading?: boolean;
  error?: string | null;
  /** Requests the timeline again after a failed load. */
  onRetry?: () => void;
}) {
  const headingId = useId();
  const ready = !loading && !error;
  const days = groupByLocalDay(events);

  return (
    <div className="pv-timeline">
      <section className="pv-timeline-section" aria-labelledby={headingId}>
        <header className="pv-timeline-section-head">
          <div><p className="pv-detail-kicker">Clinical history</p>
          <h2 id={headingId} className="pv-timeline-section-title">Recorded events</h2></div>
          {ready && events.length > 0 ? (
            <span className="pv-timeline-count">
              {events.length} {events.length === 1 ? "event" : "events"}
            </span>
          ) : null}
        </header>

        <div className="pv-timeline-list">
          {loading ? <LoadingSkeleton label="Loading timeline" lines={3} /> : null}

          {!loading && error ? (
            <div className="pv-timeline-alert" role="alert">
              <p className="pv-timeline-alert-text">{error}</p>
              {onRetry ? (
                <button type="button" onClick={onRetry} className="pv-timeline-retry">
                  Try again
                </button>
              ) : null}
            </div>
          ) : null}

          {ready && events.length === 0 ? (
            <div className="pv-timeline-card pv-timeline-empty">
              <IconChip Icon={CalendarIcon} surface="var(--surface-2)" ink="var(--ink-3)" size="md" />
              <div className="min-w-0">
                <p className="pv-timeline-empty-title">No events recorded yet</p>
                <p className="pv-timeline-empty-text">
                  Events appear here as they are recorded in this app: medications started or
                  discontinued, doses marked, symptoms reported, condition changes and safety analyses.
                </p>
              </div>
            </div>
          ) : null}

          {ready
            ? days.map((day, index) => (
                <section key={`${day.key}-${index}`} className="pv-timeline-day" aria-label={day.label}>
                  <div className="pv-timeline-date-rail">
                  <h3 className="pv-timeline-day-title">
                    {day.dateTime ? <time dateTime={day.dateTime}>{day.label}</time> : day.label}
                  </h3>
                  <p className="pv-timeline-day-count">{day.events.length} {day.events.length === 1 ? "entry that day" : "entries that day"}</p>
                  </div>
                  <ol className="pv-timeline-events">
                    {day.events.map((event) => (
                      <TimelineEvent key={event.id} event={event} />
                    ))}
                  </ol>
                </section>
              ))
            : null}
        </div>
      </section>
    </div>
  );
}

function TimelineEvent({ event }: { event: TimelineEventResponse }) {
  const tone = toneFor(event.event_type);
  const facts = eventFacts(event);

  return (
    <li className="pv-timeline-event">
      <div className="pv-timeline-marker">
        <time dateTime={event.event_time} className="pv-timeline-event-time">
          {formatEventTime(event.event_time)}
        </time>
        <IconChip Icon={tone.Icon} surface={tone.surface} ink={tone.ink} size="md" />
      </div>
      <div className="pv-timeline-event-body">
        <p className="pv-timeline-event-meta">
          <span className="pv-timeline-event-type">{eventTypeLabel(event.event_type)}</span>
        </p>
        <h4 className="pv-timeline-event-title">{event.event_title}</h4>
        {event.event_description ? (
          <p className="pv-timeline-event-text">{event.event_description}</p>
        ) : null}
        {facts.severity || facts.notes.length > 0 ? (
          <div className="pv-timeline-event-facts">
            {facts.severity ? (
              <span className="pv-timeline-severity">
                <span className="sr-only">Severity: </span>
                <SeverityPill severity={facts.severity} />
              </span>
            ) : null}
            {facts.notes.map((note) => (
              <span key={note} className="pv-timeline-note">{note}</span>
            ))}
          </div>
        ) : null}
      </div>
    </li>
  );
}
