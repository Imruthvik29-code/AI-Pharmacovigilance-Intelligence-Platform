"use client";

import type { CSSProperties } from "react";
import { CATEGORIES, categoryIndex, type CategoryId } from "@/components/patient/categories";

/**
 * The vertical category ribbons standing behind the foreground card.
 *
 * Each ribbon owns a slot in the rail. When the active category changes the
 * ribbons physically slide between slots along the same easing as the cards,
 * and the newly active one slides left under the card as it fades — it has
 * become the card in front. They are real buttons, not decorative divs.
 */
export function RibbonRail({
  activeId,
  onSelect,
  dragX,
  dragging,
}: {
  activeId: CategoryId;
  onSelect: (id: CategoryId) => void;
  dragX: number;
  dragging: boolean;
}) {
  const active = categoryIndex(activeId);

  return (
    <div
      className="pv-rail"
      style={{
        transform: `translate3d(${dragX * 0.12}px, 0, 0)`,
        transition: dragging ? "none" : "transform var(--stack-ms) var(--stack-ease)",
      }}
    >
      {CATEGORIES.map((category, index) => {
        const merged = index === active;
        // Rank among the categories still standing in the rail.
        const slot = index < active ? index : index - 1;

        return (
          <button
            key={category.id}
            type="button"
            onClick={() => onSelect(category.id)}
            aria-label={`Show ${category.label}`}
            aria-current={merged ? "true" : undefined}
            tabIndex={merged ? -1 : undefined}
            className={`pv-rail-tab ${merged ? "pv-rail-tab-merged" : ""}`}
            style={
              {
                "--slot": merged ? 0 : slot,
                backgroundColor: category.surface,
                color: category.ink,
              } as CSSProperties
            }
          >
            <span className="pv-rail-label" aria-hidden="true">
              {category.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
