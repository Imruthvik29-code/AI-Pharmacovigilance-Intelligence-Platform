import { describe, expect, it } from "vitest";
import {
  activeMedicationCount,
  demographicLine,
  evidenceSources,
  findingBreakdown,
  peakSeverity,
  severitySummary,
  unresolvedSymptomCount,
} from "@/lib/patient/summaries";
import type { AnalysisRunResponse, MedicationResponse, SymptomResponse } from "@/lib/api/types";

function run(overrides: Partial<AnalysisRunResponse> = {}): AnalysisRunResponse {
  return {
    id: "run-1",
    patient_id: "patient-1",
    analysis_version: "v1.0",
    safety_score: 74,
    risk_level: "moderate",
    deterministic_result: {
      safety_score: 74,
      risk_level: "moderate",
      starting_score: 100,
      total_points_deducted: 26,
      interaction_findings: [
        {
          interaction_rule_id: "i1",
          drug_a_id: "a",
          drug_a_name: "A",
          drug_b_id: "b",
          drug_b_name: "B",
          severity: "severe",
          mechanism: null,
          recommendation: null,
          source: "FDA Label",
        },
      ],
      adr_findings: [
        {
          adr_rule_id: "r1",
          drug_id: "a",
          drug_name: "A",
          reaction_description: "Bruising",
          severity: "moderate",
          frequency_class: null,
          source: "FDA Label",
        },
      ],
      adherence_findings: [],
      penalties: [],
    },
    llm_summary: null,
    llm_reasoning: null,
    llm_recommendations: null,
    confidence_score: null,
    confidence_level: null,
    created_at: "2026-09-09T10:00:00Z",
    ...overrides,
  };
}

describe("findingBreakdown", () => {
  it("counts interaction and ADR findings and groups them by recorded severity", () => {
    const breakdown = findingBreakdown(run());
    expect(breakdown).toEqual({
      total: 2,
      interactions: 1,
      adrs: 1,
      bySeverity: { severe: 1, moderate: 1, mild: 0 },
    });
  });

  it("returns null rather than zeros when there is no run", () => {
    expect(findingBreakdown(null)).toBeNull();
  });

  it("returns null when the deterministic result is missing", () => {
    expect(findingBreakdown(run({ deterministic_result: null }))).toBeNull();
  });

  it("reports zero findings for an empty but present result", () => {
    const breakdown = findingBreakdown(
      run({
        deterministic_result: {
          safety_score: 100,
          risk_level: "low",
          starting_score: 100,
          total_points_deducted: 0,
          interaction_findings: [],
          adr_findings: [],
          adherence_findings: [],
          penalties: [],
        },
      }),
    );
    expect(breakdown?.total).toBe(0);
  });
});

describe("peakSeverity", () => {
  it("returns the highest severity actually present", () => {
    expect(peakSeverity(run())).toBe("severe");
  });

  it("returns null when there are no findings", () => {
    expect(peakSeverity(run({ deterministic_result: null }))).toBeNull();
  });
});

describe("severitySummary", () => {
  it("lists only severities that occur", () => {
    expect(severitySummary(findingBreakdown(run()))).toBe("1 severe · 1 moderate");
  });

  it("is empty when there is nothing to summarise", () => {
    expect(severitySummary(null)).toBe("");
  });
});

describe("evidenceSources", () => {
  it("returns the distinct sources the payload actually carries", () => {
    expect(evidenceSources(run())).toEqual(["FDA Label"]);
  });

  it("never substitutes a source when the field is null", () => {
    const withoutSources = run({
      deterministic_result: {
        safety_score: 74,
        risk_level: "moderate",
        starting_score: 100,
        total_points_deducted: 26,
        interaction_findings: [
          {
            interaction_rule_id: "i1",
            drug_a_id: "a",
            drug_a_name: "A",
            drug_b_id: "b",
            drug_b_name: "B",
            severity: "severe",
            mechanism: null,
            recommendation: null,
            source: null,
          },
        ],
        adr_findings: [],
        adherence_findings: [],
        penalties: [],
      },
    });
    expect(evidenceSources(withoutSources)).toEqual([]);
  });
});

describe("record counts", () => {
  const medications = [
    { status: "active" },
    { status: "completed" },
    { status: "active" },
  ] as MedicationResponse[];
  const symptoms = [
    { resolved_date: null },
    { resolved_date: "2026-09-01" },
  ] as SymptomResponse[];

  it("counts active medications only", () => {
    expect(activeMedicationCount(medications)).toBe(2);
  });

  it("counts unresolved symptoms only", () => {
    expect(unresolvedSymptomCount(symptoms)).toBe(1);
  });
});

describe("demographicLine", () => {
  it("joins only the fields that are present", () => {
    expect(demographicLine({ age: 42, sex: "Female", relation: "Self" })).toBe(
      "42 yrs · Female · My profile",
    );
  });

  it("does not invent demographics", () => {
    expect(demographicLine({ age: null, sex: null })).toBe("No demographics recorded");
  });
});
