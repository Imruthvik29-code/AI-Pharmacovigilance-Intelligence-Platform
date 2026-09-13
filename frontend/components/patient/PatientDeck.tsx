"use client";

import { useCallback } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { patientInitials } from "@/components/PatientAvatar";
import { ArrowRightIcon } from "@/components/icons/Icons";
import { useStackSwipe } from "@/lib/hooks/useStackSwipe";
import type { PatientResponse } from "@/lib/api/types";

/**
 * The directory's deck of PATIENTS.
 *
 * Distinct from `PatientCardStack`, which is a deck of the four CATEGORIES
 * inside one patient's workspace. The two share `useStackSwipe` — one gesture
 * system, one set of commit thresholds — and nothing else: patient order,
 * layout and card content are this component's alone.
 *
 * Every patient is the same card. The selected one is in front at full
 * strength; the ones behind step right, shrink and wash towards the canvas, so
 * a drag brings the next patient forward continuously rather than swapping one
 * card's contents for another's.
 *
 * Cards carry name, age, sex, relation and initials — nothing derived, no
 * photo, no metric.
 */

/** How many cards stay visible behind the front one. Matches `--deck-depth`. */
const DEPTH = 2;
/** Each layer back loses this much scale, which is what exposes its edge. */
const SCALE_STEP = 0.05;
/** How far behind the front a card can drift before it stops being drawn. */
const CULL = DEPTH + 1.2;

function demographics(patient: PatientResponse): string {
  return [patient.age != null ? `${patient.age} yrs` : null, patient.sex].filter(Boolean).join(" · ");
}

/** Relation in the supported vocabulary; "Self" reads naturally as a label. */
function relationLabel(patient: PatientResponse): string | null {
  if (!patient.relation) return null;
  return patient.relation === "Self" ? "My profile" : patient.relation;
}

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

export function PatientDeck({
  patients,
  activeIndex,
  onSelect,
  onOpen,
}: {
  /** Already ordered by the directory — self first, then stable API order. */
  patients: PatientResponse[];
  activeIndex: number;
  onSelect: (index: number) => void;
  onOpen: (patient: PatientResponse) => void;
}) {
  const onMove = useCallback(
    (delta: number) => onSelect(activeIndex + delta),
    [activeIndex, onSelect],
  );

  const { stageRef, step, dragX, dragging, handlers } = useStackSwipe({
    index: activeIndex,
    count: patients.length,
    onMove,
  });

  const active = patients[activeIndex];

  /**
   * Changing the selection unmounts the select button of whichever card moves
   * to the front — the front card has none — so focus would fall to the body
   * and the next arrow press would go nowhere. Every path that changes the
   * selection hands focus back to the deck, which is the element that owns the
   * arrow keys, so keyboard users can step through the whole deck.
   */
  function select(index: number) {
    onSelect(index);
    stageRef.current?.focus();
  }

  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    handlers.onKeyDown(event);
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") stageRef.current?.focus();
  }

  return (
    <section aria-label="Patients">
      <div
        ref={stageRef}
        className="pv-deck"
        tabIndex={0}
        role="group"
        aria-label={`Patient ${activeIndex + 1} of ${patients.length}. Use the arrow keys to move through the deck.`}
        {...handlers}
        onKeyDown={onKeyDown}
      >
        {patients.map((patient, index) => {
          // Continuous position in the deck: 0 is the front, positive is
          // behind, negative is on its way off to the left.
          const p = index - activeIndex + (step ? dragX / step : 0);
          const depth = clamp(p, 0, DEPTH);
          const gone = Math.min(p, 0);

          // A card leaving travels the full stage width so it clears the
          // screen; a card behind only steps by the deck's own offset.
          const x = `calc(${gone} * ${step || 0}px + ${depth} * var(--deck-x))`;
          const scale = 1 - depth * SCALE_STEP;
          // A card on its way out stays nearly solid while any of it is still
          // on screen — it is leaving, not dissolving.
          const opacity = p < 0 ? clamp(1 + p * 0.5, 0, 1) : clamp(1 + (DEPTH - p), 0, 1);
          const isFront = index === activeIndex;
          const relation = relationLabel(patient);
          const meta = demographics(patient);

          return (
            <div
              key={patient.id}
              className={`pv-deck-card ${dragging ? "" : "pv-deck-card-moving"}`}
              style={{
                transform: `translate3d(${x}, 0, 0) scale(${scale})`,
                opacity,
                zIndex: 100 - Math.round(p * 10),
                visibility: p < -1.2 || p > CULL ? "hidden" : "visible",
              }}
            >
              {/* Content belongs to the card in front. It fades out over the
                  first layer back so a receded card shows only its edge — not
                  a slice of someone else's name or CTA — and fades in again as
                  a drag carries the next patient forward. */}
              <div
                className="pv-deck-body"
                style={{ opacity: clamp(1 - depth, 0, 1) }}
                aria-hidden={!isFront}
                inert={!isFront || undefined}
              >
                <span aria-hidden="true" className="pv-initials h-14 w-14 text-lg sm:h-16 sm:w-16 sm:text-xl">
                  {patientInitials(patient.name)}
                </span>
                <span className="mt-auto w-full pt-6">
                  {relation ? (
                    <span className="pv-relation pv-relation-on-dark mb-3">{relation}</span>
                  ) : null}
                  <span className="pv-deck-name block">{patient.name}</span>
                  {meta ? <span className="pv-deck-meta block">{meta}</span> : null}
                </span>
                <button
                  type="button"
                  onClick={() => onOpen(patient)}
                  aria-label={`View ${patient.name}`}
                  className="pv-cta pv-cta-invert mt-6"
                >
                  <span className="truncate">View patient</span>
                  <span className="pv-cta-badge" aria-hidden="true">
                    <ArrowRightIcon className="h-5 w-5" />
                  </span>
                </button>
              </div>

              <span
                className="pv-deck-veil"
                aria-hidden="true"
                style={{ opacity: clamp(depth, 0, DEPTH) * 0.34 }}
              />

              {/* Only the exposed edge is reachable — the front card covers the
                  rest — so this doubles as the tap target and the tab stop. */}
              {isFront ? null : (
                <button
                  type="button"
                  className="pv-deck-pick"
                  aria-label={`Show ${patient.name}`}
                  onClick={() => select(index)}
                />
              )}
            </div>
          );
        })}
      </div>

      {patients.length > 1 ? (
        <div className="pv-dots" aria-hidden="true">
          {patients.map((patient, index) => (
            <span
              key={patient.id}
              className={`pv-dot ${index === activeIndex ? "pv-dot-on" : ""}`}
            />
          ))}
        </div>
      ) : null}

      <p role="status" aria-live="polite" className="sr-only">
        {active ? `${active.name} selected, ${activeIndex + 1} of ${patients.length}` : ""}
      </p>
    </section>
  );
}
