import { Disclaimer } from "@/components/Disclaimer";
import { SafetyScoreCard } from "@/components/SafetyScoreCard";
import { parseDeterministicResult } from "@/lib/analysis/deterministic";
import type { AnalysisRunResponse, SeverityLevel } from "@/lib/api/types";

const severityClass: Record<SeverityLevel, string> = {
  severe: "bg-[#fdf2f4] text-high",
  moderate: "bg-[#fdf6ec] text-moderate",
  mild: "bg-[#eef7f4] text-low",
};

function Badge({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${className ?? ""}`}
    >
      {children}
    </span>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return <p className="text-sm leading-6 text-muted">{children}</p>;
}

function ReportSection({
  eyebrow,
  title,
  children,
}: {
  eyebrow?: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-line bg-card shadow-[0_1px_2px_rgba(20,32,41,0.04)]">
      <div className="border-b border-line px-5 py-4">
        {eyebrow ? (
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">{eyebrow}</p>
        ) : null}
        <h3 className={`${eyebrow ? "mt-1" : ""} text-base font-semibold tracking-tight`}>{title}</h3>
      </div>
      <div className="px-5 pb-5">{children}</div>
    </section>
  );
}

export function AnalysisReport({ run }: { run: AnalysisRunResponse }) {
  const result = parseDeterministicResult(run.deterministic_result);
  const interactionCount = result?.interaction_findings.length ?? 0;
  const adrCount = result?.adr_findings.length ?? 0;
  const adherenceCount = result?.adherence_findings.length ?? 0;
  const llmAvailable = Boolean(run.llm_summary);

  return (
    <article className="space-y-5" aria-label="Safety analysis report">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">Latest assessment</p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight">Safety findings</h2>
        </div>
        <p className="text-xs text-muted">
          Version {run.analysis_version} · {new Date(run.created_at).toLocaleString()}
        </p>
      </header>

      <SafetyScoreCard safetyScore={run.safety_score} riskLevel={run.risk_level} />

      <section className="grid gap-3 sm:grid-cols-3" aria-label="Finding counts">
        <Metric label="Interactions" value={interactionCount} />
        <Metric label="ADRs" value={adrCount} />
        <Metric
          label="Adherence records"
          value={adherenceCount}
          hint={adherenceCount === 0 ? "No dose history in this run" : undefined}
        />
      </section>

      <ReportSection eyebrow="Decision trace" title="Penalty summary">
        <p className="pt-4 text-xs leading-5 text-muted">
          Point deductions recorded with this analysis. This page does not recalculate them.
        </p>
        {result && result.penalties.length > 0 ? (
          <ul className="mt-2 divide-y divide-line">
            {result.penalties.map((penalty, index) => (
              <li key={`${penalty.category}-${index}`} className="flex items-start justify-between gap-4 py-3">
                <div>
                  <p className="text-sm font-medium">{penalty.description}</p>
                  <p className="mt-1 text-[11px] uppercase tracking-wide text-muted">{penalty.category}</p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <Badge className={severityClass[penalty.severity]}>{penalty.severity}</Badge>
                  <span className="font-mono text-sm">−{penalty.points}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="mt-3"><EmptyNote>No penalties were recorded for this run.</EmptyNote></div>
        )}
      </ReportSection>

      <ReportSection eyebrow="Deterministic engine" title="Drug interactions">
        {result && result.interaction_findings.length > 0 ? (
          <ul className="space-y-3 pt-4">
            {result.interaction_findings.map((finding) => (
              <li key={finding.interaction_rule_id} className="rounded-xl border border-line bg-paper/35 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium">{finding.drug_a_name} + {finding.drug_b_name}</p>
                  <Badge className={severityClass[finding.severity]}>{finding.severity}</Badge>
                </div>
                {finding.mechanism ? <p className="mt-3 text-sm leading-6">{finding.mechanism}</p> : null}
                {finding.recommendation ? <p className="mt-2 text-sm leading-6 text-muted">{finding.recommendation}</p> : null}
                {finding.source ? <p className="mt-3 text-xs text-muted">Source · {finding.source}</p> : null}
              </li>
            ))}
          </ul>
        ) : (
          <div className="pt-4"><EmptyNote>No interaction findings in this analysis.</EmptyNote></div>
        )}
      </ReportSection>

      <ReportSection eyebrow="Deterministic engine" title="Adverse drug reactions">
        {result && result.adr_findings.length > 0 ? (
          <ul className="space-y-3 pt-4">
            {result.adr_findings.map((finding) => (
              <li key={finding.adr_rule_id} className="rounded-xl border border-line bg-paper/35 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium">
                    {finding.drug_name}
                    <span className="font-normal text-muted"> · {finding.reaction_description}</span>
                  </p>
                  <Badge className={severityClass[finding.severity]}>{finding.severity}</Badge>
                </div>
                <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted">
                  {finding.frequency_class ? <span>Frequency · {finding.frequency_class}</span> : null}
                  {finding.source ? <span>Source · {finding.source}</span> : null}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="pt-4"><EmptyNote>No ADR findings in this analysis.</EmptyNote></div>
        )}
      </ReportSection>

      {result && result.adherence_findings.length > 0 ? (
        <ReportSection eyebrow="Observed history" title="Adherence">
          <ul className="divide-y divide-line pt-1">
            {result.adherence_findings.map((finding) => (
              <li key={finding.medication_id} className="py-3 text-sm">
                <span className="font-medium">{finding.drug_name}</span>
                <span className="text-muted">
                  {" "}· taken {finding.taken} / due {finding.due}
                  {finding.adherence_rate == null ? "" : ` · ${Math.round(finding.adherence_rate * 100)}%`}
                </span>
              </li>
            ))}
          </ul>
        </ReportSection>
      ) : null}

      <ReportSection eyebrow="Explain, don't decide" title="AI explanation">
        <div className="flex flex-wrap items-center justify-between gap-2 pt-4">
          <p className="text-xs leading-5 text-muted">Generated from the recorded deterministic findings.</p>
          {run.confidence_score !== null && run.confidence_level ? (
            <p className="text-[11px] uppercase tracking-wide text-muted">
              Confidence · {run.confidence_level} ({run.confidence_score})
            </p>
          ) : null}
        </div>
        {llmAvailable ? (
          <div className="mt-3 space-y-3 text-sm leading-6">
            <p>{run.llm_summary}</p>
            {run.llm_reasoning ? (
              <div><p className="text-[11px] font-semibold uppercase tracking-wide text-muted">Reasoning</p><p className="mt-1">{run.llm_reasoning}</p></div>
            ) : null}
            {run.llm_recommendations ? (
              <div><p className="text-[11px] font-semibold uppercase tracking-wide text-muted">Recommendations</p><p className="mt-1">{run.llm_recommendations}</p></div>
            ) : null}
            <p className="border-t border-line pt-3 text-xs leading-5 text-muted">
              The language model explains deterministic findings. It does not compute the safety score or invent rules.
            </p>
          </div>
        ) : (
          <div className="mt-3 rounded-xl bg-paper px-4 py-3">
            <p className="text-sm text-muted">AI explanation unavailable for this analysis.</p>
            <p className="mt-1 text-xs text-muted">The safety score and findings above still come from the rule engines.</p>
          </div>
        )}
      </ReportSection>

      <Disclaimer />
    </article>
  );
}

function Metric({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-card px-4 py-4 shadow-[0_1px_2px_rgba(20,32,41,0.04)]">
      <p className="text-[11px] uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 font-mono text-3xl font-semibold tracking-tight">{value}</p>
      {hint ? <p className="mt-1 text-xs leading-5 text-muted">{hint}</p> : null}
    </div>
  );
}
