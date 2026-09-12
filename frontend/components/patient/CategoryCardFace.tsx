"use client";

import { IconChip } from "@/components/ui/IconChip";
import { PrimaryCTA } from "@/components/ui/PrimaryCTA";
import { briefRows, type WorkspaceData } from "@/components/patient/categoryBrief";
import type { Category, CategoryId } from "@/components/patient/categories";

/**
 * The face of one deck card: tinted icon chip, title, short description, the
 * compact metadata rows, and the primary CTA pinned to the foot — the
 * reference's card anatomy.
 */
export function CategoryCardFace({
  category,
  data,
  isActive,
  onOpen,
  onRunAnalysis,
  analysisRunning,
}: {
  category: Category;
  data: WorkspaceData;
  isActive: boolean;
  onOpen: (id: CategoryId) => void;
  onRunAnalysis?: () => void;
  analysisRunning?: boolean;
}) {
  const rows = briefRows(category.id, data);
  const offerRun = category.id === "safety" && !data.analysis && Boolean(onRunAnalysis);

  return (
    <>
      <IconChip
        Icon={category.Icon}
        surface={category.surface}
        ink={category.ink}
        size="lg"
        className="sm:h-14 sm:w-14"
      />

      <h2 className="pv-card-title mt-3 lg:mt-4">{category.label}</h2>
      <p className="pv-card-desc line-clamp-3 sm:line-clamp-4">{category.description}</p>

      <ul className="mt-auto space-y-2 pt-4 sm:space-y-2.5 lg:space-y-3">
        {rows.map((row) => (
          <li key={row.key} className="flex items-start gap-2">
            <span className="mt-px flex-none" style={{ color: row.ink }} aria-hidden="true">
              <row.Icon className="h-[1.0625rem] w-[1.0625rem]" />
            </span>
            <span className="min-w-0">
              <span className="block text-[0.8125rem] font-medium leading-[1.35] text-ink-2 sm:text-[0.9375rem] lg:text-[0.875rem]">
                {row.text}
              </span>
              {row.sub ? (
                <span className="mt-0.5 block text-[0.75rem] leading-[1.35] text-ink-3 sm:text-[0.8125rem]">
                  {row.sub}
                </span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>

      <div className="pt-4">
        {offerRun ? (
          <PrimaryCTA
            onClick={onRunAnalysis}
            disabled={analysisRunning}
            busy={analysisRunning}
            tabIndex={isActive ? undefined : -1}
          >
            {analysisRunning ? "Running analysis…" : "Run analysis"}
          </PrimaryCTA>
        ) : (
          <PrimaryCTA
            onClick={() => onOpen(category.id)}
            ariaLabel={`Open ${category.label} details`}
            tabIndex={isActive ? undefined : -1}
          >
            View details
          </PrimaryCTA>
        )}
      </div>
    </>
  );
}
