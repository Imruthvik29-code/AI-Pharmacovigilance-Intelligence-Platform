"use client";

import { useCallback } from "react";
import { CategoryCardFace } from "@/components/patient/CategoryCardFace";
import { RibbonRail } from "@/components/patient/RibbonRail";
import { type WorkspaceData } from "@/components/patient/categoryBrief";
import { CATEGORIES, categoryIndex, type CategoryId } from "@/components/patient/categories";
import { useStackSwipe } from "@/lib/hooks/useStackSwipe";

/**
 * The deck of CATEGORIES inside one patient's workspace.
 *
 * Not to be confused with the directory's deck of PATIENTS — the two share the
 * `useStackSwipe` gesture only; ordering, layout and content stay separate.
 *
 * Cards are real, physically positioned surfaces: all four are laid out
 * absolutely and translated by their distance from the active index, so a
 * gesture moves the cards themselves rather than swapping text inside one
 * card. Tapping a ribbon or pressing an arrow key animates along the same
 * paths, so pointer, touch and keyboard all read as the same physical deck.
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
  const active = categoryIndex(activeId);

  const onMove = useCallback(
    (delta: number) => {
      const next = CATEGORIES[active + delta];
      if (next) onSelect(next.id);
    },
    [active, onSelect],
  );

  const { stageRef, step, dragX, dragging, handlers } = useStackSwipe({
    index: active,
    count: CATEGORIES.length,
    onMove,
  });

  return (
    <section aria-label="Patient workspace">
      <div ref={stageRef} className="pv-stage" {...handlers}>
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
