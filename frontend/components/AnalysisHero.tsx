import { AnalysisReport } from "@/components/AnalysisReport";
import { CardSkeleton } from "@/components/LoadingSkeleton";
import { StatusBanner } from "@/components/StatusBanner";
import type { AnalysisRunResponse } from "@/lib/api/types";

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
    <div className="space-y-3" aria-busy={running}>
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
        <section className="rounded-row bg-surface-2 px-5 py-8">
          <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-ink-3">
            Analysis report
          </p>
          <h2 className="mt-2 text-[1.0625rem] font-semibold tracking-[-0.01em]">No analysis yet</h2>
          <p className="mt-2 max-w-xl text-[0.875rem] leading-6 text-ink-2">
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
