import { CardSkeleton } from "@/components/LoadingSkeleton";
import { StatusBanner } from "@/components/StatusBanner";
import { parseDeterministicResult } from "@/lib/analysis/deterministic";
import { primaryButtonClass } from "@/lib/ui/classes";
import type { AnalysisRunResponse, SeverityLevel } from "@/lib/api/types";

const severityStyle: Record<SeverityLevel, string> = {
  severe: "border-[#efc9cf] bg-[#fdf2f4] text-high",
  moderate: "border-[#efd9b9] bg-[#fdf6ec] text-moderate",
  mild: "border-[#cde4dc] bg-[#eef7f4] text-low",
};

function label(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function SafetyDetail({
  run,
  historyError,
  historyLoaded,
  running,
  onRunAnalysis,
}: {
  run: AnalysisRunResponse | null;
  historyError: string | null;
  historyLoaded: boolean;
  running: boolean;
  onRunAnalysis: () => void;
}) {
  const result = parseDeterministicResult(run?.deterministic_result ?? null);
  const findings = result ? [...result.interaction_findings, ...result.adr_findings] : [];
  const severityCounts = findings.reduce<Record<SeverityLevel, number>>(
    (counts, finding) => ({ ...counts, [finding.severity]: counts[finding.severity] + 1 }),
    { mild: 0, moderate: 0, severe: 0 },
  );

  return (
    <section id="safety" aria-labelledby="safety-heading" className="mt-8 max-w-3xl scroll-mt-6 overflow-hidden rounded-[2rem] border border-line bg-card shadow-[0_12px_32px_rgba(20,32,41,0.06)]">
      <header className="border-b border-line px-5 py-6 sm:px-7">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">01 · Safety</p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <h2 id="safety-heading" className="text-2xl font-semibold tracking-tight">Safety details</h2>
          {run?.risk_level ? <span className="rounded-full bg-paper px-3 py-1 text-xs font-medium">{label(run.risk_level)} risk</span> : null}
        </div>
      </header>

      <div className="divide-y divide-line" aria-busy={running}>
        {historyError ? <div className="p-5 sm:px-7"><StatusBanner tone="error" role="alert">Could not load analysis history. {historyError}</StatusBanner></div> : null}
        {running ? <div className="p-5 sm:px-7"><StatusBanner tone="info">Running analysis… Previous findings stay visible until the new result arrives.</StatusBanner></div> : null}
        {running && !run ? <div className="p-5 sm:px-7"><CardSkeleton label="Running analysis" /></div> : null}

        {findings.length > 0 ? (
          <div className="flex items-start gap-4 bg-[#fff6f2] px-5 py-5 sm:px-7" role="status">
            <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-[#f9dfd8] text-high" aria-hidden="true">!</span>
            <div>
              <p className="font-semibold">{findings.length} deterministic {findings.length === 1 ? "finding" : "findings"}</p>
              <p className="mt-1 text-sm text-muted">
                {(["severe", "moderate", "mild"] as const).filter((severity) => severityCounts[severity] > 0).map((severity) => `${severityCounts[severity]} ${severity}`).join(" · ")}
              </p>
            </div>
          </div>
        ) : null}

        {run?.created_at ? (
          <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-4 sm:px-7">
            <p className="text-sm font-medium">Latest analysis</p>
            <time dateTime={run.created_at} className="text-sm text-muted">{new Date(run.created_at).toLocaleString()}</time>
          </div>
        ) : null}

        {result?.interaction_findings.map((finding) => (
          <article key={finding.interaction_rule_id} className={`border-l-4 px-5 py-5 sm:px-7 ${severityStyle[finding.severity]}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em]">Drug interaction</p>
              <span className="rounded-full border border-current/20 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide">{finding.severity}</span>
            </div>
            <h3 className="mt-2 font-semibold text-ink">{finding.drug_a_name} + {finding.drug_b_name}</h3>
            {finding.mechanism ? <p className="mt-2 text-sm leading-6 text-ink">{finding.mechanism}</p> : null}
            {finding.recommendation ? <p className="mt-2 text-sm leading-6 text-muted">{finding.recommendation}</p> : null}
            {finding.source ? <p className="mt-3 text-xs text-muted">Source · {finding.source}</p> : null}
          </article>
        ))}

        {result?.adr_findings.map((finding) => (
          <article key={finding.adr_rule_id} className={`border-l-4 px-5 py-5 sm:px-7 ${severityStyle[finding.severity]}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em]">Adverse drug reaction</p>
              <span className="rounded-full border border-current/20 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide">{finding.severity}</span>
            </div>
            <h3 className="mt-2 font-semibold text-ink">{finding.drug_name}</h3>
            <p className="mt-2 text-sm leading-6 text-ink">{finding.reaction_description}</p>
            {(finding.frequency_class || finding.source) ? <p className="mt-3 text-xs text-muted">{[finding.frequency_class ? `Frequency · ${finding.frequency_class}` : null, finding.source ? `Source · ${finding.source}` : null].filter(Boolean).join(" · ")}</p> : null}
          </article>
        ))}

        {!running && !run && historyLoaded && !historyError ? <div className="px-5 py-8 sm:px-7"><h3 className="font-semibold">No analysis yet</h3><p className="mt-2 text-sm leading-6 text-muted">Run analysis to check the current medication record.</p></div> : null}
        {!running && !run && !historyLoaded && !historyError ? <div className="p-5 sm:px-7"><CardSkeleton label="Loading analysis" /></div> : null}
        {run && result && findings.length === 0 ? <div className="px-5 py-6 sm:px-7"><p className="font-medium">No interaction or ADR findings</p><p className="mt-1 text-sm text-muted">No deterministic interaction or adverse reaction findings were recorded in this run.</p></div> : null}
      </div>

      <footer className="border-t border-line bg-paper/40 p-5 sm:px-7">
        <button type="button" onClick={onRunAnalysis} disabled={running} className={`${primaryButtonClass} w-full justify-center`}>
          {running ? "Running analysis…" : "Run analysis"}
        </button>
      </footer>
    </section>
  );
}
