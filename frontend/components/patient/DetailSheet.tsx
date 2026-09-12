"use client";

import { useEffect, useRef } from "react";
import { IconChip } from "@/components/ui/IconChip";
import { getCategory, type CategoryId } from "@/components/patient/categories";

/**
 * The one container for a category's detail view. Replaces the previous
 * positional `.detail-toolbar ~ section { … !important }` styling.
 *
 * Moves focus to its heading when the category changes so keyboard and screen
 * reader users land on the new content instead of staying on a removed control.
 */
export function DetailSheet({
  categoryId,
  title,
  meta,
  footer,
  children,
}: {
  categoryId: CategoryId;
  title: string;
  meta?: string;
  /** Primary action, rendered at the end of the sheet. */
  footer?: React.ReactNode;
  children: React.ReactNode;
}) {
  const category = getCategory(categoryId);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, [categoryId]);

  return (
    <section className="px-sheet" aria-labelledby="detail-heading">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3.5">
          <IconChip Icon={category.Icon} surface={category.surface} ink={category.ink} size="lg" />
          <div className="min-w-0">
            <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-ink-3">
              {category.number} · {category.label}
            </p>
            <h2
              id="detail-heading"
              ref={headingRef}
              tabIndex={-1}
              className="px-detail-heading mt-1 text-[1.5rem] font-semibold tracking-[-0.015em] sm:text-[1.75rem]"
            >
              {title}
            </h2>
            <p className="mt-1.5 max-w-xl text-[0.875rem] leading-6 text-ink-2">
              {meta ?? category.description}
            </p>
          </div>
        </div>
      </div>

      <div className="mt-6 space-y-6">{children}</div>

      {footer ? <div className="mt-7 border-t border-hairline pt-6">{footer}</div> : null}
    </section>
  );
}
