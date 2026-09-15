import { AnalysisReport } from "@/components/AnalysisReport";
import { CardSkeleton } from "@/components/LoadingSkeleton";
import { StatusBanner } from "@/components/StatusBanner";
import type { AnalysisRunResponse } from "@/lib/api/types";

/**
 * The Safety detail's content in every state: history error, run in progress,
 * the stored report, no analysis yet, and loading. `pv-safety` is present in
 * all of them so the Safety reading surface applies to the whole screen.
 */
export function AnalysisHero({
  run,
  historyError,
  historyLoaded,
  running,
}: {
  run: AnalysisRunResponse | null;
  historyError: string | null;
  historyLoaded: boolean;
  running: boolean;
}) {
  return (
    <div className="pv-safety" aria-busy={running}>
      {historyError ? (
        <StatusBanner tone="error" role="alert">
          Could not load analysis history. {historyError}
        </StatusBanner>
      ) : null}

      {running ? (
        <StatusBanner tone="info">
          Running analysis… Previous findings stay visible until the new report arrives.
        </StatusBanner>
      ) : null}

      {running && !run ? <CardSkeleton label="Running analysis" /> : null}

      {run ? <AnalysisReport run={run} /> : null}

      {!running && !run && historyLoaded && !historyError ? (
        <section className="pv-safety-card pv-safety-empty">
          <h2 className="pv-safety-empty-title">No analysis yet</h2>
          <p className="pv-safety-empty-text">
            Add medications, then run analysis to generate a safety report from this patient’s
            current record.
          </p>
        </section>
      ) : null}

      {!running && !run && !historyLoaded && !historyError ? (
        <CardSkeleton label="Loading analysis" />
      ) : null}
    </div>
  );
}
