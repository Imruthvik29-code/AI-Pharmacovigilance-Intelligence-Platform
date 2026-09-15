import type { ComponentType } from "react";
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
import type { AnalysisRunResponse, SeverityLevel } from "@/lib/api/types";

const SEVERITY_TONE = {
  severe: { surface: "var(--severe-bg)", ink: "var(--severe-fg)" },
  moderate: { surface: "var(--moderate-bg)", ink: "var(--moderate-fg)" },
  mild: { surface: "var(--mild-bg)", ink: "var(--mild-fg)" },
} as const;

/** "1 finding" / "2 findings" — reported, never computed. */
function countLabel(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** A section of the report: a plain heading, an optional quiet note, its content. */
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

/** The shared severity badge, set at the report's reading size. */
function Severity({ severity }: { severity: SeverityLevel }) {
  return (
    <span className="pv-safety-severity">
      <SeverityPill severity={severity} />
    </span>
  );
}

/**
 * One group of findings as its own card: an icon-chip header naming the group,
 * then its findings — or, when there are none, the recorded empty statement as
 * the header's second line.
 */
function FindingGroup({
  title,
  Icon,
  count,
  emptyText,
  children,
}: {
  title: string;
  Icon: ComponentType<{ className?: string }>;
  count: number;
  emptyText: string;
  children: React.ReactNode;
}) {
  const hasFindings = count > 0;
  return (
    <div className="pv-safety-card pv-safety-group">
      <div className="pv-safety-group-head">
        <IconChip
          Icon={Icon}
          surface={hasFindings ? "var(--safety-bg)" : "var(--surface-2)"}
          ink={hasFindings ? "var(--safety-fg)" : "var(--ink-3)"}
          size="md"
        />
        <div className="pv-safety-group-copy">
          <h3 className="pv-safety-group-title">{title}</h3>
          {hasFindings ? (
            <p className="pv-safety-group-meta">{countLabel(count, "finding")}</p>
          ) : (
            <p className="pv-safety-group-meta pv-safety-group-none">{emptyText}</p>
          )}
        </div>
      </div>
      {hasFindings ? <ul className="pv-safety-items">{children}</ul> : null}
    </div>
  );
}

/**
 * The Safety reading screen: one summary of the recorded run, the individual
 * deterministic findings, how the recorded score was reached, and the language
 * model's explanation, kept visibly secondary.
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
              <p className="pv-safety-fact-sub">{formatDateTime(run.created_at)}</p>
              <p className="pv-safety-fact-version">version {run.analysis_version}</p>
            </div>
          </div>
        </div>
      </section>

      <Section title="Findings" note="Identified by the safety rules.">
        <div className="pv-safety-groups">
          <FindingGroup
            title="Drug interactions"
            Icon={AlertIcon}
            count={interactionCount}
            emptyText="No interaction findings in this analysis."
          >
            {result?.interaction_findings.map((finding) => (
              <li key={finding.interaction_rule_id} className="pv-safety-item">
                <div className="pv-safety-item-head">
                  <p className="pv-safety-item-title">
                    {finding.drug_a_name} + {finding.drug_b_name}
                  </p>
                  <Severity severity={finding.severity} />
                </div>
                {finding.mechanism ? <p className="pv-safety-item-text">{finding.mechanism}</p> : null}
                {finding.recommendation ? (
                  <p className="pv-safety-item-text pv-safety-item-emphasis">{finding.recommendation}</p>
                ) : null}
                {finding.source ? <p className="pv-safety-item-meta">Source · {finding.source}</p> : null}
              </li>
            ))}
          </FindingGroup>

          <FindingGroup
            title="Adverse drug reactions"
            Icon={PulseIcon}
            count={adrCount}
            emptyText="No ADR findings in this analysis."
          >
            {result?.adr_findings.map((finding) => (
              <li key={finding.adr_rule_id} className="pv-safety-item">
                <div className="pv-safety-item-head">
                  <p className="pv-safety-item-title">{finding.drug_name}</p>
                  <Severity severity={finding.severity} />
                </div>
                <p className="pv-safety-item-text pv-safety-item-emphasis">{finding.reaction_description}</p>
                {finding.frequency_class || finding.source ? (
                  <p className="pv-safety-item-meta">
                    {finding.frequency_class ? <span>Frequency · {finding.frequency_class}</span> : null}
                    {finding.source ? <span>Source · {finding.source}</span> : null}
                  </p>
                ) : null}
              </li>
            ))}
          </FindingGroup>
        </div>

        {sources.length > 0 ? (
          <p className="pv-safety-sources">
            <DocumentIcon className="pv-safety-sources-icon" />
            <span>Evidence sources · {sources.join(" · ")}</span>
          </p>
        ) : null}
      </Section>

      <Section title="Score deductions" note="Recorded with this analysis and not recalculated here.">
        <div className="pv-safety-card pv-safety-rows">
          {result && result.penalties.length > 0 ? (
            <ul className="pv-safety-items">
              {result.penalties.map((penalty, index) => (
                <li key={`${penalty.category}-${index}`} className="pv-safety-item pv-safety-row">
                  <div className="min-w-0 flex-1">
                    <p className="pv-safety-item-title">{penalty.description}</p>
                    <p className="pv-safety-item-meta pv-safety-category">
                      {penalty.category.replace(/_/g, " ")}
                    </p>
                  </div>
                  <div className="pv-safety-trailing">
                    <Severity severity={penalty.severity} />
                    <span className="pv-safety-points">−{penalty.points}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="pv-safety-none">No penalties were recorded for this run.</p>
          )}
        </div>
      </Section>

      {result && result.adherence_findings.length > 0 ? (
        <Section
          title="Adherence"
          aside={<span className="pv-safety-count">{countLabel(adherenceCount, "record")}</span>}
        >
          <div className="pv-safety-card pv-safety-rows">
            <ul className="pv-safety-items">
              {result.adherence_findings.map((finding) => (
                <li key={finding.medication_id} className="pv-safety-item pv-safety-row">
                  <div className="min-w-0 flex-1">
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
          </div>
        </Section>
      ) : null}

      <Section
        title="AI explanation"
        note="Written from the recorded findings above."
        aside={
          run.confidence_score !== null && run.confidence_level ? (
            <span className="pv-safety-confidence">
              Confidence · {run.confidence_level} ({run.confidence_score})
            </span>
          ) : null
        }
      >
        <div className="pv-safety-explanation">
          {llmAvailable ? (
            <>
              <p className="pv-safety-lead">{run.llm_summary}</p>
              {run.llm_reasoning ? (
                <div>
                  <h3 className="pv-safety-sub-label">Reasoning</h3>
                  <p className="pv-safety-sub-text">{run.llm_reasoning}</p>
                </div>
              ) : null}
              {run.llm_recommendations ? (
                <div>
                  <h3 className="pv-safety-sub-label">Recommendations</h3>
                  <p className="pv-safety-sub-text">{run.llm_recommendations}</p>
                </div>
              ) : null}
              <p className="pv-safety-footnote">
                AI explains the findings above. It does not set the safety score or add findings.
              </p>
            </>
          ) : (
            <>
              <p className="pv-safety-unavailable-title">AI explanation unavailable for this analysis.</p>
              <p className="pv-safety-footnote">
                The safety score and findings above come from the safety rules.
              </p>
            </>
          )}
        </div>
      </Section>

      <div className="pv-safety-disclaimer">
        <Disclaimer compact />
      </div>
    </article>
  );
}
