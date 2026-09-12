"use client";

import { CATEGORIES, type CategoryId } from "@/components/patient/categories";

/**
 * Segmented category strip shown in the detail context, so switching between
 * Safety / Medications / Symptoms / Timeline never requires returning to the
 * overview first. Four equal segments — it never scrolls horizontally.
 */
export function CategoryTabs({
  activeId,
  onSelect,
}: {
  activeId: CategoryId;
  onSelect: (id: CategoryId) => void;
}) {
  return (
    <div className="px-tabs" role="group" aria-label="Clinical categories">
      {CATEGORIES.map((category) => {
        const active = category.id === activeId;
        return (
          <button
            key={category.id}
            type="button"
            onClick={() => onSelect(category.id)}
            aria-current={active ? "true" : undefined}
            className={`px-tab ${active ? "px-tab-active" : ""}`}
          >
            <span className="truncate px-1">{category.label}</span>
          </button>
        );
      })}
    </div>
  );
}
