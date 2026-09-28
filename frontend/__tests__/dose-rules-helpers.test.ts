import { describe, expect, it } from "vitest";
import type { MedicationResponse, PatientResponse } from "@/lib/api/types";
import {
  describeRule,
  draftsToPayload,
  emptyDraft,
  ruleProblem,
  ruleScheduleProblem,
  type DoseRuleDraft,
} from "@/lib/medications/doseRules";

const draft = (patch: Partial<DoseRuleDraft>): DoseRuleDraft => ({ ...emptyDraft(), ...patch });

const patient: PatientResponse = {
  id: "p1", user_id: "u1", name: "P", relation: null, age: null, sex: null, weight_kg: null,
  renal_flag: false, hepatic_flag: false, timezone: "Asia/Kolkata",
  breakfast_time: "08:00:00", lunch_time: null, dinner_time: "20:00:00",
  created_at: "", updated_at: "",
};

function med(over: Partial<MedicationResponse>): MedicationResponse {
  return {
    id: "m1", patient_id: "p1", condition_id: null, purpose_text: null, drug_id: "d1",
    dose: "1 tablet", times_per_day: 2, interval_hours: null, duration_days: 5,
    status: "active", start_date: "2026-10-01", end_date: null, created_at: "", updated_at: "",
    drug_name: "Examplecin", drug_generic_name: null, drug_term_type: null, drug_source: null,
    dose_rules: [],
    ...over,
  };
}

const rule = (sequence: number, over: Record<string, unknown> = {}) => ({
  id: `r${sequence}`, medication_id: "m1", sequence, anchor_type: "breakfast" as const,
  anchor_relation: "with" as const, offset_minutes: null, clock_time: null, dose: null,
  created_at: "", updated_at: "", ...over,
});

describe("ruleProblem", () => {
  it("requires an anchor before anything else", () => {
    expect(ruleProblem(draft({}))).toMatch(/choose when/i);
  });

  it("requires a relation for a meal anchor", () => {
    expect(ruleProblem(draft({ anchor: "lunch" }))).toMatch(/before, with or after/i);
  });

  it("accepts 'with' without an offset", () => {
    expect(ruleProblem(draft({ anchor: "lunch", relation: "with" }))).toBeNull();
  });

  it.each(["", "0", "61", "1.5", "-3", "abc"])("rejects before/after offset %j", (offset) => {
    expect(ruleProblem(draft({ anchor: "dinner", relation: "after", offset }))).toMatch(/1–60/);
  });

  it.each(["1", "30", "60"])("accepts before/after offset %s", (offset) => {
    expect(ruleProblem(draft({ anchor: "dinner", relation: "before", offset }))).toBeNull();
  });

  it("requires a time for a specific-time rule", () => {
    expect(ruleProblem(draft({ anchor: "clock_time" }))).toMatch(/enter a time/i);
    expect(ruleProblem(draft({ anchor: "clock_time", clock: "21:00" }))).toBeNull();
  });
});

describe("draftsToPayload", () => {
  it("assigns contiguous sequences from list order", () => {
    const payload = draftsToPayload([
      draft({ anchor: "dinner", relation: "with" }),
      draft({ anchor: "breakfast", relation: "with" }),
      draft({ anchor: "lunch", relation: "with" }),
    ]);
    expect(payload.map((r) => r.sequence)).toEqual([1, 2, 3]);
    expect(payload.map((r) => r.anchor_type)).toEqual(["dinner", "breakfast", "lunch"]);
  });

  it("sends no relation or offset for a specific-time rule", () => {
    const [rule0] = draftsToPayload([draft({ anchor: "clock_time", clock: "21:00", relation: "after", offset: "10" })]);
    expect(rule0).toEqual({ sequence: 1, anchor_type: "clock_time", clock_time: "21:00", dose: null });
  });

  it("sends no offset for 'with'", () => {
    const [rule0] = draftsToPayload([draft({ anchor: "lunch", relation: "with", offset: "15" })]);
    expect(rule0).toEqual({ sequence: 1, anchor_type: "lunch", anchor_relation: "with", dose: null });
  });

  it("sends the offset as a number for before/after", () => {
    const [rule0] = draftsToPayload([draft({ anchor: "breakfast", relation: "before", offset: "30" })]);
    expect(rule0).toMatchObject({ anchor_relation: "before", offset_minutes: 30 });
  });

  it("sends a blank amount as null so the course dose is inherited", () => {
    const [blank, set] = draftsToPayload([
      draft({ anchor: "lunch", relation: "with", dose: "   " }),
      draft({ anchor: "dinner", relation: "with", dose: "half tablet" }),
    ]);
    expect(blank.dose).toBeNull();
    expect(set.dose).toBe("half tablet");
  });

  it("returns an empty list for an empty collection, never null", () => {
    expect(draftsToPayload([])).toEqual([]);
  });
});

describe("describeRule", () => {
  it("describes each rule shape", () => {
    expect(describeRule(rule(1, { anchor_relation: "with" }))).toBe("With breakfast");
    expect(describeRule(rule(1, { anchor_type: "dinner", anchor_relation: "before", offset_minutes: 30 })))
      .toBe("30 min before dinner");
    expect(describeRule(rule(1, { anchor_type: "clock_time", anchor_relation: null, clock_time: "21:00:00" })))
      .toMatch(/^At /);
  });
});

describe("ruleScheduleProblem", () => {
  it("leaves courses without rules to the existing checks", () => {
    expect(ruleScheduleProblem(med({ dose_rules: [] }), patient)).toBeNull();
    expect(ruleScheduleProblem(med({ dose_rules: undefined }), patient)).toBeNull();
  });

  it("reports a rule count that does not match times_per_day", () => {
    expect(ruleScheduleProblem(med({ times_per_day: 2, dose_rules: [rule(1)] }), patient))
      .toBe("1 of 2 dose timings set.");
  });

  it("reports rules combined with an interval", () => {
    expect(ruleScheduleProblem(med({ interval_hours: 8, dose_rules: [rule(1)] }), patient))
      .toMatch(/interval are both set/);
  });

  it("reports a missing timezone", () => {
    expect(ruleScheduleProblem(
      med({ times_per_day: 1, dose_rules: [rule(1)] }),
      { ...patient, timezone: null },
    )).toMatch(/timezone is not recorded/);
  });

  it("names the meal whose routine time is missing", () => {
    expect(ruleScheduleProblem(
      med({ times_per_day: 1, dose_rules: [rule(1, { anchor_type: "lunch" })] }),
      patient,
    )).toBe("Lunch time is not recorded in the patient's daily routine.");
  });

  it("needs no routine time for a specific-time rule", () => {
    expect(ruleScheduleProblem(
      med({ times_per_day: 1, dose_rules: [rule(1, { anchor_type: "clock_time", anchor_relation: null, clock_time: "21:00:00" })] }),
      patient,
    )).toBeNull();
  });

  it("is satisfied when rules, frequency and routine agree", () => {
    expect(ruleScheduleProblem(
      med({ times_per_day: 2, dose_rules: [rule(1), rule(2, { anchor_type: "dinner" })] }),
      patient,
    )).toBeNull();
  });
});
