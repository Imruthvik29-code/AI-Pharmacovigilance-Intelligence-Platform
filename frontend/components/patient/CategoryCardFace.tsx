"use client";

import { IconChip } from "@/components/ui/IconChip";
import { PrimaryCTA } from "@/components/ui/PrimaryCTA";
import { briefRows, type WorkspaceData } from "@/components/patient/categoryBrief";
import type { Category, CategoryId } from "@/components/patient/categories";

/**
 * Whether this category has nothing on record yet. Presentation only: the rows
 * and their wording come from `briefRows` unchanged; an empty category just
 * sets them as a quiet line instead of an inset summary panel.
 */
function hasNoRecord(id: CategoryId, data: WorkspaceData): boolean {
  if (id === "safety") return !data.analysis;
  if (id === "medications") return data.medications.length === 0;
  if (id === "symptoms") return data.symptoms.length === 0;
  return data.timeline.length === 0;
}

/**
 * The face of one deck card, in the reference's reading order: tinted icon
 * chip, title, short description, the recorded summary grouped in a quiet inset
 * panel, then the primary action directly beneath it.
 *
 * Header and summary read as one sequence. Any height the deck has beyond this
 * card's own content opens between the description and the summary, so the
 * summary and its action always stay together.
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
  const empty = hasNoRecord(category.id, data);
  const offerRun = category.id === "safety" && !data.analysis && Boolean(onRunAnalysis);

  return (
    <>
      <IconChip
        Icon={category.Icon}
        surface={category.surface}
        ink={category.ink}
        size="lg"
        className="pv-card-chip"
      />

      <h2 className="pv-card-title">{category.label}</h2>
      <p className="pv-card-desc">{category.description}</p>

      <ul className={`pv-card-summary ${empty ? "pv-card-summary-empty" : ""}`}>
        {rows.map((row) => (
          <li key={row.key} className="pv-card-row">
            <span
              className="pv-card-row-icon"
              style={empty ? undefined : { color: row.ink }}
              aria-hidden="true"
            >
              <row.Icon className="h-4 w-4" />
            </span>
            <span className="min-w-0">
              <span className="pv-card-row-text">{row.text}</span>
              {row.sub ? <span className="pv-card-row-sub">{row.sub}</span> : null}
            </span>
          </li>
        ))}
      </ul>

      <div className="pv-card-action">
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
