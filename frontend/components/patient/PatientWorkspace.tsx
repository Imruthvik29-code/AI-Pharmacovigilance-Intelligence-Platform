"use client";

import { useRef } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import { IconChip } from "@/components/ui/IconChip";
import { PillButton } from "@/components/ui/PillButton";
import { CategoryRibbon } from "@/components/patient/CategoryRibbon";
import { briefRows, briefSummary, type WorkspaceData } from "@/components/patient/categoryBrief";
import {
  CATEGORIES,
  categoryIndex,
  getCategory,
  type CategoryId,
} from "@/components/patient/categories";

const SWIPE_THRESHOLD = 48;

/**
 * Patient overview: one foreground card for the active category with the other
 * three emerging from behind its right edge.
 *
 * Selecting a category swaps the card in place; opening it replaces the whole
 * overview with that category's detail view (owned by the page). Tapping a
 * ribbon always works — swipe is an addition, never the only route, and no
 * control is disabled during the swap, so keyboard focus is never dropped.
 */
export function PatientWorkspace({
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
  const pointerStart = useRef<number | null>(null);
  const category = getCategory(activeId);
  const index = categoryIndex(activeId);
  const rows = briefRows(activeId, data);
  const summaries = Object.fromEntries(
    CATEGORIES.map((item) => [item.id, briefSummary(item.id, data)]),
  ) as Record<CategoryId, string>;

  function step(delta: number) {
    const next = CATEGORIES[index + delta];
    if (next) onSelect(next.id);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      step(1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      step(-1);
    }
  }

  function handlePointerDown(event: PointerEvent<HTMLElement>) {
    if (event.target instanceof HTMLElement && event.target.closest("button, a")) return;
    pointerStart.current = event.clientX;
  }

  function handlePointerUp(event: PointerEvent<HTMLElement>) {
    const start = pointerStart.current;
    pointerStart.current = null;
    if (start === null) return;
    const delta = event.clientX - start;
    if (Math.abs(delta) < SWIPE_THRESHOLD) return;
    step(delta < 0 ? 1 : -1);
  }

  const showRunAnalysis = activeId === "safety" && !data.analysis && Boolean(onRunAnalysis);

  return (
    <section aria-label="Patient workspace">
      <div
        className="px-stage"
        onKeyDown={handleKeyDown}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerCancel={() => {
          pointerStart.current = null;
        }}
      >
        <article className="px-card" aria-labelledby="category-heading">
          <IconChip Icon={category.Icon} surface={category.surface} ink={category.ink} size="lg" />

          <p className="mt-4 text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-ink-3">
            {category.number} / {String(CATEGORIES.length).padStart(2, "0")}
          </p>
          <h2
            id="category-heading"
            className="mt-1 text-[1.625rem] font-semibold leading-tight tracking-[-0.015em] sm:text-[1.875rem]"
          >
            {category.label}
          </h2>
          <p className="mt-2 text-[0.875rem] leading-6 text-ink-2">{category.description}</p>

          {/* Plain inline icons, as in the reference — a filled chip per row
              would eat the card's limited text measure. */}
          <ul className="mt-5 space-y-3">
            {rows.map((row) => (
              <li key={row.key} className="flex items-start gap-2">
                <span className="mt-px flex-none" style={{ color: row.ink }}>
                  <row.Icon className="h-[1.15rem] w-[1.15rem]" />
                </span>
                <span className="min-w-0">
                  <span className="block text-[0.8125rem] leading-[1.4] text-ink-2 lg:text-[0.875rem]">
                    {row.text}
                  </span>
                  {row.sub ? (
                    <span className="mt-0.5 block text-[0.75rem] leading-[1.4] text-ink-3">
                      {row.sub}
                    </span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>

          <div className="mt-6 pt-1 sm:mt-auto">
            {showRunAnalysis ? (
              <PillButton
                onClick={onRunAnalysis}
                disabled={analysisRunning}
                busy={analysisRunning}
                width="block"
              >
                {analysisRunning ? "Running analysis…" : "Run analysis"}
              </PillButton>
            ) : (
              <PillButton
                onClick={() => onOpen(activeId)}
                ariaLabel={`Open ${category.label} details`}
                width="block"
              >
                View details
              </PillButton>
            )}
          </div>
        </article>

        <CategoryRibbon activeId={activeId} onSelect={onSelect} summaries={summaries} />
      </div>

      <div className="px-dots" aria-hidden="true">
        {CATEGORIES.map((item) => (
          <span
            key={item.id}
            className={`px-dot ${item.id === activeId ? "px-dot-active" : ""}`}
          />
        ))}
      </div>

      <p role="status" aria-live="polite" className="sr-only">
        {category.label} selected
      </p>
    </section>
  );
}
