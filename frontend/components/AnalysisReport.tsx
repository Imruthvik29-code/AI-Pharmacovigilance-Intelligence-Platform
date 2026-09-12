import { Disclaimer } from "@/components/Disclaimer";
import { SafetyScoreCard } from "@/components/SafetyScoreCard";
import { IconChip } from "@/components/ui/IconChip";
import { SeverityPill } from "@/components/ui/SeverityPill";
import {
  AlertIcon,
  CheckIcon,
  ClockIcon,
  DocumentIcon,
  PulseIcon,
  SparkIcon,
} from "@/components/icons/Icons";
import { StatRow } from "@/components/ui/StatRow";
import { parseDeterministicResult } from "@/lib/analysis/deterministic";
import {
  evidenceSources,
  findingBreakdown,
  formatDateTime,
  peakSeverity,
  severitySummary,
} from "@/lib/patient/summaries";
import type { AnalysisRunResponse } from "@/lib/api/types";

const SEVERITY_TONE = {
  severe: { surface: "var(--severe-bg)", ink: "var(--severe-fg)" },
  moderate: { surface: "var(--moderate-bg)", ink: "var(--moderate-fg)" },
  mild: { surface: "var(--mild-bg)", ink: "var(--mild-fg)" },
} as const;

/** "1 finding" / "2 findings" — reported, never computed. */
function countLabel(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-row bg-surface-2 px-4 py-3.5 text-[0.8125rem] leading-5 text-ink-2">
      {children}
    </p>
  );
}

function Block({
  eyebrow,
  title,
  meta,
  children,
}: {
  eyebrow?: string;
  title: string;
  meta?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1 px-0.5">
        <div>
          {eyebrow ? <p className="pv-eyebrow">{eyebrow}</p> : null}
          <h3 className="pv-section-title mt-0.5">{title}</h3>
        </div>
        {meta ? <div className="text-[0.75rem] text-ink-3">{meta}</div> : null}
      </div>
      <div className="mt-3 space-y-2">{children}</div>
    </section>
  );
}

export function AnalysisReport({ run }: { run: AnalysisRunResponse }) {
  const result = parseDeterministicResult(run.deterministic_result);
  const interactionCount = result?.interaction_findings.length ?? 0;
  const adrCount = result?.adr_findings.length ?? 0;
  const adherenceCount = result?.adherence_findings.length ?? 0;
  const llmAvailable = Boolean(run.llm_summary);

  const breakdown = findingBreakdown(run);
  const severity = peakSeverity(run);
  const split = severitySummary(breakdown);
  const sources = evidenceSources(run);
  const alertTone = severity ? SEVERITY_TONE[severity] : SEVERITY_TONE.mild;

  return (
    <article className="space-y-5" aria-label="Safety analysis report">
      {breakdown ? (
        <div
          className="flex items-center gap-3 rounded-md px-4 py-3.5"
          style={{ backgroundColor: alertTone.surface }}
        >
          <IconChip
            Icon={breakdown.total > 0 ? AlertIcon : CheckIcon}
            surface="rgb(255 255 255 / 0.72)"
            ink={alertTone.ink}
            size="md"
          />
          <div className="min-w-0">
            <p className="text-[0.9375rem] font-semibold" style={{ color: alertTone.ink }}>
              {breakdown.total === 0
                ? "No interaction or ADR findings identified"
                : `${breakdown.total} safety ${breakdown.total === 1 ? "finding" : "findings"} identified`}
            </p>
            {split ? (
              <p className="mt-0.5 text-[0.8125rem]" style={{ color: alertTone.ink, opacity: 0.85 }}>
                {split}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      <SafetyScoreCard safetyScore={run.safety_score} riskLevel={run.risk_level} />

      <StatRow
        Icon={ClockIcon}
        surface="var(--surface-2)"
        ink="var(--ink-2)"
        title="Last analysis"
        meta={formatDateTime(run.created_at)}
        trailing={
          <span className="pv-row-meta flex-none">version {run.analysis_version}</span>
        }
      />

      <Block
        eyebrow="Deterministic engine"
        title="Drug interactions"
        meta={countLabel(interactionCount, "finding")}
      >
        {result && result.interaction_findings.length > 0 ? (
          <ul className="space-y-2">
            {result.interaction_findings.map((finding) => (
              <li key={finding.interaction_rule_id} className="pv-row items-start">
                <IconChip
                  Icon={AlertIcon}
                  surface={SEVERITY_TONE[finding.severity].surface}
                  ink={SEVERITY_TONE[finding.severity].ink}
                  size="sm"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold tracking-[-0.01em]">
                      {finding.drug_a_name} + {finding.drug_b_name}
                    </p>
                    <SeverityPill severity={finding.severity} />
                  </div>
                  {finding.mechanism ? (
                    <p className="mt-1.5 text-[0.8125rem] leading-5 text-ink-2">{finding.mechanism}</p>
                  ) : null}
                  {finding.recommendation ? (
                    <p className="mt-1 text-[0.8125rem] leading-5 text-ink-2">
                      {finding.recommendation}
                    </p>
                  ) : null}
                  {finding.source ? (
                    <p className="mt-2 text-[0.75rem] text-ink-3">Source · {finding.source}</p>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyNote>No interaction findings in this analysis.</EmptyNote>
        )}
      </Block>

      <Block
        eyebrow="Deterministic engine"
        title="Adverse drug reactions"
        meta={countLabel(adrCount, "finding")}
      >
        {result && result.adr_findings.length > 0 ? (
          <ul className="space-y-2">
            {result.adr_findings.map((finding) => (
              <li key={finding.adr_rule_id} className="pv-row items-start">
                <IconChip
                  Icon={PulseIcon}
                  surface={SEVERITY_TONE[finding.severity].surface}
                  ink={SEVERITY_TONE[finding.severity].ink}
                  size="sm"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold tracking-[-0.01em]">
                      {finding.drug_name}
                      <span className="font-normal text-ink-2"> · {finding.reaction_description}</span>
                    </p>
                    <SeverityPill severity={finding.severity} />
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-x-3 text-[0.75rem] text-ink-3">
                    {finding.frequency_class ? <span>Frequency · {finding.frequency_class}</span> : null}
                    {finding.source ? <span>Source · {finding.source}</span> : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyNote>No ADR findings in this analysis.</EmptyNote>
        )}
      </Block>

      <Block eyebrow="Decision trace" title="Penalty summary">
        {result && result.penalties.length > 0 ? (
          <ul className="space-y-2">
            {result.penalties.map((penalty, index) => (
              <li key={`${penalty.category}-${index}`} className="pv-row">
                <div className="min-w-0 flex-1">
                  <p className="text-[0.9375rem] font-medium">{penalty.description}</p>
                  <p className="mt-0.5 text-[0.75rem] uppercase tracking-[0.1em] text-ink-3">
                    {penalty.category}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2.5">
                  <SeverityPill severity={penalty.severity} />
                  <span className="font-mono text-[0.9375rem] font-semibold">−{penalty.points}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyNote>No penalties were recorded for this run.</EmptyNote>
        )}
        <p className="px-1 text-[0.75rem] leading-5 text-ink-3">
          Point deductions recorded with this analysis. This page does not recalculate them.
        </p>
      </Block>

      {result && result.adherence_findings.length > 0 ? (
        <Block
          eyebrow="Observed history"
          title="Adherence"
          meta={countLabel(adherenceCount, "record")}
        >
          <ul className="space-y-2">
            {result.adherence_findings.map((finding) => (
              <li key={finding.medication_id} className="pv-row">
                <span className="min-w-0 flex-1 text-[0.875rem]">
                  <span className="font-semibold">{finding.drug_name}</span>
                  <span className="text-ink-2">
                    {" "}
                    · taken {finding.taken} / due {finding.due}
                    {finding.adherence_rate == null
                      ? ""
                      : ` · ${Math.round(finding.adherence_rate * 100)}%`}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </Block>
      ) : null}

      {sources.length > 0 ? (
        <Block eyebrow="Provenance" title="Evidence sources">
          <div className="pv-row">
            <IconChip
              Icon={DocumentIcon}
              surface="var(--surface-2)"
              ink="var(--ink-2)"
              size="sm"
            />
            <p className="min-w-0 flex-1 text-[0.8125rem] leading-5 text-ink-2">
              {sources.join(" · ")}
            </p>
          </div>
        </Block>
      ) : null}

      <Block
        eyebrow="Explain, don't decide"
        title="AI explanation"
        meta={
          run.confidence_score !== null && run.confidence_level ? (
            <span className="uppercase tracking-[0.1em]">
              Confidence · {run.confidence_level} ({run.confidence_score})
            </span>
          ) : null
        }
      >
        <div className="pv-row flex-col items-start gap-3">
          <p className="text-[0.75rem] leading-5 text-ink-3">
            Generated from the recorded deterministic findings.
          </p>
          {llmAvailable ? (
            <div className="space-y-3 text-[0.875rem] leading-6">
              <p className="flex gap-2.5">
                <IconChip
                  Icon={SparkIcon}
                  surface="var(--mild-bg)"
                  ink="var(--mild-fg)"
                  size="sm"
                />
                <span>{run.llm_summary}</span>
              </p>
              {run.llm_reasoning ? (
                <div>
                  <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.12em] text-ink-3">
                    Reasoning
                  </p>
                  <p className="mt-1">{run.llm_reasoning}</p>
                </div>
              ) : null}
              {run.llm_recommendations ? (
                <div>
                  <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.12em] text-ink-3">
                    Recommendations
                  </p>
                  <p className="mt-1">{run.llm_recommendations}</p>
                </div>
              ) : null}
              <p className="border-t border-line pt-3 text-[0.75rem] leading-5 text-ink-3">
                The language model explains deterministic findings. It does not compute the safety
                score or invent rules.
              </p>
            </div>
          ) : (
            <div>
              <p className="text-[0.875rem] text-ink-2">AI explanation unavailable for this analysis.</p>
              <p className="mt-1 text-[0.75rem] text-ink-3">
                The safety score and findings above still come from the rule engines.
              </p>
            </div>
          )}
        </div>
      </Block>

      <Disclaimer />
    </article>
  );
}
