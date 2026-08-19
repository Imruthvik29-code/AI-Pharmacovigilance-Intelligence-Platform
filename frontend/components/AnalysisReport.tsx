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
      className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${className ?? ""}`}
    >
      {children}
    </span>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>;
}

export function AnalysisReport({ run }: { run: AnalysisRunResponse }) {
  const result = parseDeterministicResult(run.deterministic_result);
  const interactionCount = result?.interaction_findings.length ?? 0;
  const adrCount = result?.adr_findings.length ?? 0;
  const adherenceCount = result?.adherence_findings.length ?? 0;
  const llmAvailable = Boolean(run.llm_summary);

  return (
    <article className="space-y-5" aria-label="Safety analysis report">
      <header>
        <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-accent">
          Analysis report
        </p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Safety findings</h2>
        <p className="mt-1 text-sm text-muted">
          Version {run.analysis_version} · {new Date(run.created_at).toLocaleString()}
        </p>
      </header>

      <SafetyScoreCard safetyScore={run.safety_score} riskLevel={run.risk_level} />

      <section className="grid gap-3 sm:grid-cols-3">
        <Metric label="Interactions" value={interactionCount} />
        <Metric label="ADRs" value={adrCount} />
        <Metric
          label="Adherence records"
          value={adherenceCount}
          hint={adherenceCount === 0 ? "No dose history in this run" : undefined}
        />
      </section>

      <section className="rounded-2xl border border-line bg-card p-5">
        <h3 className="text-sm font-semibold">Penalty summary</h3>
        <p className="mt-1 text-xs text-muted">
          Point deductions recorded with this analysis. This page does not recalculate them.
        </p>
        {result && result.penalties.length > 0 ? (
          <ul className="mt-4 divide-y divide-line">
            {result.penalties.map((penalty, index) => (
              <li key={`${penalty.category}-${index}`} className="flex items-start justify-between gap-4 py-3">
                <div>
                  <p className="text-sm font-medium">{penalty.description}</p>
                  <p className="mt-1 text-xs uppercase tracking-wide text-muted">{penalty.category}</p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <Badge className={severityClass[penalty.severity]}>{penalty.severity}</Badge>
                  <span className="font-mono text-sm">−{penalty.points}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="mt-3">
            <EmptyNote>No penalties were recorded for this run.</EmptyNote>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-line bg-card p-5">
        <h3 className="text-sm font-semibold">Drug interactions</h3>
        {result && result.interaction_findings.length > 0 ? (
          <ul className="mt-4 space-y-3">
            {result.interaction_findings.map((finding) => (
              <li key={finding.interaction_rule_id} className="rounded-xl border border-line p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium">
                    {finding.drug_a_name} + {finding.drug_b_name}
                  </p>
                  <Badge className={severityClass[finding.severity]}>{finding.severity}</Badge>
                </div>
                {finding.mechanism ? (
                  <p className="mt-3 text-sm leading-6">{finding.mechanism}</p>
                ) : null}
                {finding.recommendation ? (
                  <p className="mt-2 text-sm leading-6 text-muted">{finding.recommendation}</p>
                ) : null}
                {finding.source ? (
                  <p className="mt-3 text-xs text-muted">Source · {finding.source}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <div className="mt-3">
            <EmptyNote>No interaction findings in this analysis.</EmptyNote>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-line bg-card p-5">
        <h3 className="text-sm font-semibold">Adverse drug reactions</h3>
        {result && result.adr_findings.length > 0 ? (
          <ul className="mt-4 space-y-3">
            {result.adr_findings.map((finding) => (
              <li key={finding.adr_rule_id} className="rounded-xl border border-line p-4">
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
          <div className="mt-3">
            <EmptyNote>No ADR findings in this analysis.</EmptyNote>
          </div>
        )}
      </section>

      {result && result.adherence_findings.length > 0 ? (
        <section className="rounded-2xl border border-line bg-card p-5">
          <h3 className="text-sm font-semibold">Adherence</h3>
          <ul className="mt-4 space-y-3">
            {result.adherence_findings.map((finding) => (
              <li key={finding.medication_id} className="text-sm">
                <span className="font-medium">{finding.drug_name}</span>
                <span className="text-muted">
                  {" "}
                  · taken {finding.taken} / due {finding.due}
                  {finding.adherence_rate == null
                    ? ""
                    : ` · ${Math.round(finding.adherence_rate * 100)}%`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="rounded-2xl border border-line bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">AI explanation</h3>
          {run.confidence_score !== null && run.confidence_level ? (
            <p className="text-xs uppercase tracking-wide text-muted">
              Confidence · {run.confidence_level} ({run.confidence_score})
            </p>
          ) : null}
        </div>
        {llmAvailable ? (
          <div className="mt-3 space-y-3 text-sm leading-6">
            <p>{run.llm_summary}</p>
            {run.llm_reasoning ? (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">Reasoning</p>
                <p className="mt-1">{run.llm_reasoning}</p>
              </div>
            ) : null}
            {run.llm_recommendations ? (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Recommendations
                </p>
                <p className="mt-1">{run.llm_recommendations}</p>
              </div>
            ) : null}
            <p className="text-xs text-muted">
              The language model explains deterministic findings. It does not compute the safety
              score or invent rules.
            </p>
          </div>
        ) : (
          <div className="mt-3 rounded-xl bg-paper px-4 py-3">
            <p className="text-sm text-muted">AI explanation unavailable for this analysis.</p>
            <p className="mt-1 text-xs text-muted">
              The safety score and findings above still come from the rule engines.
            </p>
          </div>
        )}
      </section>

      <Disclaimer />
    </article>
  );
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint?: string;
}) {
  return (
    <div className="rounded-2xl border border-line bg-card px-4 py-4">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 font-mono text-3xl font-semibold">{value}</p>
      {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
    </div>
  );
}
