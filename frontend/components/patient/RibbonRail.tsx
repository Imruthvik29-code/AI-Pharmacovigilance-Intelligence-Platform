"use client";

import type { CSSProperties } from "react";
import { CATEGORIES, categoryIndex, type CategoryId } from "@/components/patient/categories";

/**
 * The category cards standing behind the foreground card.
 *
 * Position follows the active index: categories before the active one stand to
 * its LEFT, categories after it to its RIGHT, each side ranked outwards from
 * the card. The adjacent card shows a strip of its surface with its icon and
 * name; cards further back show only an edge. When the active category changes
 * they physically slide between slots along the same easing as the cards, and
 * the newly active one slides under the card as it fades — it has become the
 * card in front. They are real buttons, not decorative divs.
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
        const side = merged ? "merged" : index < active ? "left" : "right";
        // Rank outwards from the card on its own side: 0 sits against the card.
        const slot = merged ? 0 : index < active ? active - 1 - index : index - active - 1;

        return (
          <button
            key={category.id}
            type="button"
            onClick={() => onSelect(category.id)}
            aria-label={`Show ${category.label}`}
            aria-current={merged ? "true" : undefined}
            tabIndex={merged ? -1 : undefined}
            className={`pv-rail-tab ${merged ? "pv-rail-tab-merged" : ""}`}
            data-side={side}
            // The card against the active one shows its name; cards further back show only an edge.
            data-depth={merged ? undefined : slot === 0 ? "adjacent" : "far"}
            style={
              {
                "--slot": slot,
                "--ribbon-tint": category.surface,
                "--ribbon-ink": category.ink,
              } as CSSProperties
            }
          >
            <category.Icon className="pv-rail-icon" />
            <span className="pv-rail-label" aria-hidden="true">
              {category.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
