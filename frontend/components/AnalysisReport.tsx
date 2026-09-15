import { Disclaimer } from "@/components/Disclaimer";
import { SafetyScoreCard } from "@/components/SafetyScoreCard";
import { IconChip } from "@/components/ui/IconChip";
import { SeverityPill } from "@/components/ui/SeverityPill";
import { AlertIcon, CheckIcon, ClockIcon, DocumentIcon, PulseIcon } from "@/components/icons/Icons";
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

/** A section of the report: one plain heading, an optional note, its content. */
function Section({
  title,
  note,
  aside,
  children,
}: {
  title: string;
  note?: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="pv-safety-section">
      <header className="pv-safety-section-head">
        <div className="pv-safety-section-row">
          <h2 className="pv-safety-section-title">{title}</h2>
          {aside}
        </div>
        {note ? <p className="pv-safety-section-note">{note}</p> : null}
      </header>
      {children}
    </section>
  );
}

/** Nothing recorded for a group: a quiet line, not a status box. */
function EmptyLine({ children }: { children: React.ReactNode }) {
  return <p className="pv-safety-empty-line">{children}</p>;
}

/**
 * The Safety reading screen: one summary of the recorded run, the individual
 * deterministic findings, how the recorded score was reached, the evidence the
 * findings cite, and the language model's explanation kept visibly separate.
 *
 * Everything shown is read from the stored analysis run. Nothing is computed,
 * re-scored or reinterpreted here.
 */
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
  const HeadlineIcon = breakdown && breakdown.total > 0 ? AlertIcon : CheckIcon;

  return (
    <article className="pv-safety-report" aria-label="Safety analysis report">
      <div>
        <section className="pv-safety-card pv-safety-summary" aria-label="Current safety summary">
          <SafetyScoreCard safetyScore={run.safety_score} riskLevel={run.risk_level} />

          <div className="pv-safety-facts">
            {breakdown ? (
              <div className="pv-safety-fact">
                <span className="pv-safety-fact-icon" style={{ color: alertTone.ink }} aria-hidden="true">
                  <HeadlineIcon className="h-[1.125rem] w-[1.125rem]" />
                </span>
                <div className="min-w-0">
                  <p className="pv-safety-fact-title" style={{ color: alertTone.ink }}>
                    {breakdown.total === 0
                      ? "No interaction or ADR findings identified"
                      : `${breakdown.total} safety ${breakdown.total === 1 ? "finding" : "findings"} identified`}
                  </p>
                  {split ? <p className="pv-safety-fact-sub">{split}</p> : null}
                </div>
              </div>
            ) : null}

            <div className="pv-safety-fact">
              <span className="pv-safety-fact-icon" aria-hidden="true">
                <ClockIcon className="h-[1.125rem] w-[1.125rem]" />
              </span>
              <div className="min-w-0">
                <p className="pv-safety-fact-title">Last analysis</p>
                <p className="pv-safety-fact-sub">
                  {formatDateTime(run.created_at)}{" "}
                  <span className="pv-safety-nowrap">· version {run.analysis_version}</span>
                </p>
              </div>
            </div>
          </div>
        </section>
        <p className="pv-safety-caption">
          Out of 100. Produced by rule engines, not by the language model.
        </p>
      </div>

      <Section title="Findings" note="From the deterministic rule engines">
        <div className="pv-safety-group">
          <h3 className="pv-safety-group-title">
            Drug interactions
            <span className="pv-safety-count">{countLabel(interactionCount, "finding")}</span>
          </h3>
          {result && result.interaction_findings.length > 0 ? (
            <ul className="pv-safety-card pv-safety-list">
              {result.interaction_findings.map((finding) => (
                <li key={finding.interaction_rule_id} className="pv-safety-item">
                  <IconChip
                    Icon={AlertIcon}
                    surface={SEVERITY_TONE[finding.severity].surface}
                    ink={SEVERITY_TONE[finding.severity].ink}
                    size="sm"
                  />
                  <div className="pv-safety-item-body">
                    <div className="pv-safety-item-head">
                      <p className="pv-safety-item-title">
                        {finding.drug_a_name} + {finding.drug_b_name}
                      </p>
                      <SeverityPill severity={finding.severity} />
                    </div>
                    {finding.mechanism ? (
                      <p className="pv-safety-item-text">{finding.mechanism}</p>
                    ) : null}
                    {finding.recommendation ? (
                      <p className="pv-safety-item-text pv-safety-item-emphasis">
                        {finding.recommendation}
                      </p>
                    ) : null}
                    {finding.source ? (
                      <p className="pv-safety-item-meta">Source · {finding.source}</p>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyLine>No interaction findings in this analysis.</EmptyLine>
          )}
        </div>

        <div className="pv-safety-group">
          <h3 className="pv-safety-group-title">
            Adverse drug reactions
            <span className="pv-safety-count">{countLabel(adrCount, "finding")}</span>
          </h3>
          {result && result.adr_findings.length > 0 ? (
            <ul className="pv-safety-card pv-safety-list">
              {result.adr_findings.map((finding) => (
                <li key={finding.adr_rule_id} className="pv-safety-item">
                  <IconChip
                    Icon={PulseIcon}
                    surface={SEVERITY_TONE[finding.severity].surface}
                    ink={SEVERITY_TONE[finding.severity].ink}
                    size="sm"
                  />
                  <div className="pv-safety-item-body">
                    <div className="pv-safety-item-head">
                      <p className="pv-safety-item-title">{finding.drug_name}</p>
                      <SeverityPill severity={finding.severity} />
                    </div>
                    <p className="pv-safety-item-text pv-safety-item-emphasis">
                      {finding.reaction_description}
                    </p>
                    {finding.frequency_class || finding.source ? (
                      <p className="pv-safety-item-meta">
                        {finding.frequency_class ? <span>Frequency · {finding.frequency_class}</span> : null}
                        {finding.source ? <span>Source · {finding.source}</span> : null}
                      </p>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyLine>No ADR findings in this analysis.</EmptyLine>
          )}
        </div>
      </Section>

      <Section title="Score deductions" note="Point deductions recorded with this analysis. This page does not recalculate them.">
        {result && result.penalties.length > 0 ? (
          <ul className="pv-safety-card pv-safety-list">
            {result.penalties.map((penalty, index) => (
              <li key={`${penalty.category}-${index}`} className="pv-safety-item">
                <div className="pv-safety-item-body">
                  <p className="pv-safety-item-title">{penalty.description}</p>
                  <p className="pv-safety-item-meta pv-safety-category">
                    {penalty.category.replace(/_/g, " ")}
                  </p>
                </div>
                <div className="pv-safety-trailing">
                  <SeverityPill severity={penalty.severity} />
                  <span className="pv-safety-points">−{penalty.points}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyLine>No penalties were recorded for this run.</EmptyLine>
        )}
      </Section>

      {result && result.adherence_findings.length > 0 ? (
        <Section
          title="Adherence"
          aside={<span className="pv-safety-count">{countLabel(adherenceCount, "record")}</span>}
        >
          <ul className="pv-safety-card pv-safety-list">
            {result.adherence_findings.map((finding) => (
              <li key={finding.medication_id} className="pv-safety-item">
                <div className="pv-safety-item-body">
                  <p className="pv-safety-item-title">{finding.drug_name}</p>
                  <p className="pv-safety-item-meta">
                    taken {finding.taken} / due {finding.due}
                    {finding.adherence_rate == null
                      ? ""
                      : ` · ${Math.round(finding.adherence_rate * 100)}%`}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {sources.length > 0 ? (
        <Section title="Evidence sources">
          <p className="pv-safety-sources">
            <DocumentIcon className="pv-safety-sources-icon" />
            <span>{sources.join(" · ")}</span>
          </p>
        </Section>
      ) : null}

      <Section
        title="AI explanation"
        note="Generated from the recorded deterministic findings."
        aside={
          run.confidence_score !== null && run.confidence_level ? (
            <span className="pv-safety-confidence">
              Confidence · {run.confidence_level} ({run.confidence_score})
            </span>
          ) : null
        }
      >
        {llmAvailable ? (
          <div className="pv-safety-card pv-safety-explanation">
            <p className="pv-safety-lead">{run.llm_summary}</p>
            {run.llm_reasoning ? (
              <div className="pv-safety-subsection">
                <h3 className="pv-safety-sub-label">Reasoning</h3>
                <p className="pv-safety-sub-text">{run.llm_reasoning}</p>
              </div>
            ) : null}
            {run.llm_recommendations ? (
              <div className="pv-safety-subsection">
                <h3 className="pv-safety-sub-label">Recommendations</h3>
                <p className="pv-safety-sub-text">{run.llm_recommendations}</p>
              </div>
            ) : null}
            <p className="pv-safety-footnote">
              The language model explains deterministic findings. It does not compute the safety
              score or invent rules.
            </p>
          </div>
        ) : (
          <div className="pv-safety-unavailable">
            <p className="pv-safety-unavailable-title">AI explanation unavailable for this analysis.</p>
            <p className="pv-safety-unavailable-text">
              The safety score and findings above still come from the rule engines.
            </p>
          </div>
        )}
      </Section>

      <div className="pv-safety-disclaimer">
        <Disclaimer compact />
      </div>
    </article>
  );
}
