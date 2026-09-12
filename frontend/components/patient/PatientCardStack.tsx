"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import { CategoryCardFace } from "@/components/patient/CategoryCardFace";
import { RibbonRail } from "@/components/patient/RibbonRail";
import { type WorkspaceData } from "@/components/patient/categoryBrief";
import { CATEGORIES, categoryIndex, type CategoryId } from "@/components/patient/categories";

/** Commit a swipe past this fraction of the stage width… */
const DISTANCE_RATIO = 0.18;
/** …or above this flick velocity in px/ms, whichever happens first. */
const VELOCITY = 0.4;
/** Vertical intent beyond this abandons the horizontal gesture. */
const VERTICAL_SLOP = 12;

type Drag = { pointerId: number; startX: number; startY: number; startedAt: number };

/**
 * The category deck.
 *
 * Cards are real, physically positioned surfaces: all four are laid out
 * absolutely and translated by their distance from the active index, so a
 * gesture moves the cards themselves rather than swapping text inside one
 * card. Direction is the standard physical model —
 *
 *   swipe LEFT  → the current card travels LEFT  and the NEXT card
 *                 arrives from the RIGHT
 *   swipe RIGHT → the current card travels RIGHT and the PREVIOUS card
 *                 arrives from the LEFT
 *
 * Tapping a ribbon or pressing an arrow key animates along the same paths, so
 * pointer, touch and keyboard all read as the same physical deck.
 */
export function PatientCardStack({
  activeId,
  onSelect,
  onOpen,
  onRunAnalysis,
  analysisRunning = false,
  data,
}: {
  activeId: CategoryId;
  onSelect: (id: CategoryId) => void;
  onOpen: (id: CategoryId) => void;
  onRunAnalysis?: () => void;
  analysisRunning?: boolean;
  data: WorkspaceData;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<Drag | null>(null);
  const [dragX, setDragX] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [step, setStep] = useState(0);

  const active = categoryIndex(activeId);
  const last = CATEGORIES.length - 1;

  // A card travels the full stage width, so it clears the viewport entirely
  // instead of stopping half-way over the ribbons.
  useEffect(() => {
    const element = stageRef.current;
    if (!element) return;
    const measure = () => setStep(element.getBoundingClientRect().width);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const move = useCallback(
    (delta: number) => {
      const next = CATEGORIES[active + delta];
      if (next) onSelect(next.id);
    },
    [active, onSelect],
  );

  function endDrag() {
    dragRef.current = null;
    setDragging(false);
    setDragX(0);
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    // Controls inside the deck keep their own behaviour.
    if (event.target instanceof Element && event.target.closest("button, a")) return;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startedAt: event.timeStamp || performance.now(),
    };
    setDragging(true);
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;

    // Let the page scroll if the gesture is clearly vertical.
    if (Math.abs(dy) > VERTICAL_SLOP && Math.abs(dy) > Math.abs(dx)) {
      endDrag();
      return;
    }
    if (Math.abs(dx) < 2) return;

    try {
      if (!stageRef.current?.hasPointerCapture(event.pointerId)) {
        stageRef.current?.setPointerCapture(event.pointerId);
      }
    } catch {
      /* pointer capture is an enhancement, not a requirement */
    }

    // Resist past the ends of the deck instead of tearing free.
    const atStart = active === 0 && dx > 0;
    const atEnd = active === last && dx < 0;
    setDragX(atStart || atEnd ? dx * 0.32 : dx);
  }

  function handlePointerUp(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    const dx = event.clientX - drag.startX;
    const elapsed = Math.max(1, (event.timeStamp || performance.now()) - drag.startedAt);
    const velocity = Math.abs(dx) / elapsed;
    const threshold = (step || 320) * DISTANCE_RATIO;

    endDrag();
    if (Math.abs(dx) < 6) return;
    if (Math.abs(dx) < threshold && velocity < VELOCITY) return;
    move(dx < 0 ? 1 : -1);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      move(1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      move(-1);
    }
  }

  return (
    <section aria-label="Patient workspace">
      <div
        ref={stageRef}
        className="pv-stage"
        onKeyDown={handleKeyDown}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={endDrag}
      >
        <RibbonRail activeId={activeId} onSelect={onSelect} dragX={dragX} dragging={dragging} />

        {CATEGORIES.map((category, index) => {
          const distance = index - active;
          const offset = distance * (step || 0) + dragX;
          const ratio = step > 0 ? Math.min(Math.abs(offset) / step, 1) : Math.min(Math.abs(distance), 1);
          const isActive = index === active;
          // Neighbours stay mounted so an incoming card is already rendered.
          const near = Math.abs(distance) <= 1;

          return (
            <article
              key={category.id}
              className={`pv-card ${dragging ? "" : "pv-card-moving"}`}
              style={{
                transform: `translate3d(${offset}px, 0, 0) scale(${1 - ratio * 0.05})`,
                opacity: near ? 1 - ratio * 0.38 : 0,
                zIndex: 10 - Math.round(ratio * 8),
                pointerEvents: isActive ? "auto" : "none",
                visibility: near ? "visible" : "hidden",
              }}
              aria-hidden={isActive ? undefined : true}
              inert={isActive ? undefined : true}
            >
              <CategoryCardFace
                category={category}
                data={data}
                isActive={isActive}
                onOpen={onOpen}
                onRunAnalysis={onRunAnalysis}
                analysisRunning={analysisRunning}
              />
            </article>
          );
        })}
      </div>

      <div className="pv-dots" aria-hidden="true">
        {CATEGORIES.map((category) => (
          <span
            key={category.id}
            className={`pv-dot ${category.id === activeId ? "pv-dot-on" : ""}`}
          />
        ))}
      </div>

      <p role="status" aria-live="polite" className="sr-only">
        {CATEGORIES[active].label} selected, {active + 1} of {CATEGORIES.length}
      </p>
    </section>
  );
}
