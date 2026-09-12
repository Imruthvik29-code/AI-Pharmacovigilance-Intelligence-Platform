"use client";

import { IconChip } from "@/components/ui/IconChip";
import { CATEGORIES, type CategoryId } from "@/components/patient/categories";

/**
 * The inactive categories, emerging from behind the foreground card's right
 * edge. Below 1024px they are vertical ribbons (the reference's signature); at
 * 1024px and above the same siblings widen into a readable stacked column at
 * the same z-depth, still tucked under the card's edge.
 *
 * Only one of the two renderings is in the layout at a time (the other is
 * `display: none`, so it is also out of the accessibility tree). All four
 * categories stay reachable at every viewport — nothing is clipped or scrolled
 * off-screen.
 */
export function CategoryRibbon({
  activeId,
  onSelect,
  summaries,
}: {
  activeId: CategoryId;
  onSelect: (id: CategoryId) => void;
  summaries: Record<CategoryId, string>;
}) {
  const inactive = CATEGORIES.filter((category) => category.id !== activeId);

  return (
    <>
      <div className="px-ribbon">
        {inactive.map((category) => (
          <button
            key={category.id}
            type="button"
            onClick={() => onSelect(category.id)}
            aria-label={`Show ${category.label}`}
            className="px-ribbon-tab"
            style={{ backgroundColor: category.surface, color: category.ink }}
          >
            <span className="px-ribbon-label" aria-hidden="true">
              {category.label}
            </span>
          </button>
        ))}
      </div>

      <div className="px-ribbon-stack">
        {inactive.map((category) => (
          <button
            key={category.id}
            type="button"
            onClick={() => onSelect(category.id)}
            aria-label={`Show ${category.label}`}
            className="px-ribbon-card"
            style={{ backgroundColor: category.surface, color: category.ink }}
          >
            <span className="flex items-center gap-2.5">
              <IconChip
                Icon={category.Icon}
                surface="rgb(255 255 255 / 0.7)"
                ink={category.ink}
                size="sm"
              />
              <span className="text-[0.9375rem] font-semibold tracking-tight">{category.label}</span>
            </span>
            <span className="text-[0.8125rem] opacity-80">{summaries[category.id]}</span>
          </button>
        ))}
      </div>
    </>
  );
}
