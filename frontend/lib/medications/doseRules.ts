/**
 * Dose-rule helpers shared by the rule editor and the schedule panel.
 *
 * The backend (backend/app/schemas/dose_rule.py and the schedule endpoint)
 * is authoritative for every rule below; these helpers only let the UI
 * refuse an incoherent rule before it is sent and explain why a course is
 * not yet schedulable. They never compute a dose time -- the schedule
 * endpoint does that from the patient's routine.
 */
import type {
  DoseAnchor,
  DoseRelation,
  DoseRuleInput,
  DoseRuleResponse,
  MedicationResponse,
  PatientResponse,
} from "@/lib/api/types";

/** Mirrors MAX_OFFSET_MINUTES in backend/app/schemas/dose_rule.py. */
export const MAX_OFFSET_MINUTES = 60;

export const ANCHOR_LABELS: Record<DoseAnchor, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  clock_time: "Specific time",
};

export const RELATION_LABELS: Record<DoseRelation, string> = {
  before: "Before",
  with: "With",
  after: "After",
};

const MEAL_FIELD: Record<Exclude<DoseAnchor, "clock_time">, "breakfast_time" | "lunch_time" | "dinner_time"> = {
  breakfast: "breakfast_time",
  lunch: "lunch_time",
  dinner: "dinner_time",
};

/**
 * One rule as the editor holds it. Fields are strings, and an anchor or
 * relation may still be unchosen, so the editor can represent a rule the
 * user is part-way through. Only a draft with no problem is ever sent.
 */
export type DoseRuleDraft = {
  /** Stable React key; not sent. Rule ids are not preserved across saves. */
  key: string;
  anchor: DoseAnchor | "";
  relation: DoseRelation | "";
  offset: string;
  clock: string;
  dose: string;
};

let draftCounter = 0;
function nextKey(): string {
  draftCounter += 1;
  return `rule-${draftCounter}`;
}

/** A new rule starts with nothing chosen: no timing is assumed for the user. */
export function emptyDraft(): DoseRuleDraft {
  return { key: nextKey(), anchor: "", relation: "", offset: "", clock: "", dose: "" };
}

/** "21:00:00" -> "21:00", the value an input[type=time] expects. */
function toTimeInput(value: string | null): string {
  if (!value) return "";
  const match = /^(\d{2}):(\d{2})/.exec(value);
  return match ? `${match[1]}:${match[2]}` : "";
}

export function draftFromResponse(rule: DoseRuleResponse): DoseRuleDraft {
  return {
    key: nextKey(),
    anchor: rule.anchor_type,
    relation: rule.anchor_relation ?? "",
    offset: rule.offset_minutes != null ? String(rule.offset_minutes) : "",
    clock: toTimeInput(rule.clock_time),
    dose: rule.dose ?? "",
  };
}

function isWholeNumberInRange(value: string, min: number, max: number): boolean {
  if (!/^\d+$/.test(value.trim())) return false;
  const n = Number(value);
  return Number.isSafeInteger(n) && n >= min && n <= max;
}

/**
 * Why this draft cannot be saved, or null when it can. Mirrors the
 * backend's per-rule coherence check so an invalid rule is caught here
 * rather than as a 422.
 */
export function ruleProblem(draft: DoseRuleDraft): string | null {
  if (!draft.anchor) return "Choose when this dose is taken.";
  if (draft.anchor === "clock_time") {
    return /^\d{2}:\d{2}(:\d{2})?$/.test(draft.clock) ? null : "Enter a time.";
  }
  if (!draft.relation) return "Choose before, with or after.";
  if (draft.relation === "with") return null;
  return isWholeNumberInRange(draft.offset, 1, MAX_OFFSET_MINUTES)
    ? null
    : `Enter 1–${MAX_OFFSET_MINUTES} minutes.`;
}

/**
 * The complete collection to send. Sequences are assigned from the list
 * order, so they are always contiguous from 1 and never duplicated. Call
 * only when every draft is free of problems.
 */
export function draftsToPayload(drafts: DoseRuleDraft[]): DoseRuleInput[] {
  return drafts.map((draft, index) => {
    const dose = draft.dose.trim() || null;
    const sequence = index + 1;
    const anchor = draft.anchor as DoseAnchor;
    if (anchor === "clock_time") {
      return { sequence, anchor_type: anchor, clock_time: draft.clock, dose };
    }
    if (draft.relation === "with") {
      return { sequence, anchor_type: anchor, anchor_relation: "with", dose };
    }
    return {
      sequence,
      anchor_type: anchor,
      anchor_relation: draft.relation as DoseRelation,
      offset_minutes: Number(draft.offset),
      dose,
    };
  });
}

/**
 * Format a wall-clock "HH:MM[:SS]" for display. UTC is used only as a
 * neutral frame so the value is shown exactly as recorded -- no zone
 * conversion happens.
 */
export function formatWallClock(value: string | null | undefined): string | null {
  const match = value ? /^(\d{2}):(\d{2})/.exec(value) : null;
  if (!match) return null;
  const date = new Date(Date.UTC(2000, 0, 1, Number(match[1]), Number(match[2])));
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC",
  }).format(date);
}

/** "30 min before breakfast", "With lunch", "At 9:00 PM". */
export function describeRule(rule: Pick<DoseRuleResponse, "anchor_type" | "anchor_relation" | "offset_minutes" | "clock_time">): string {
  if (rule.anchor_type === "clock_time") {
    return `At ${formatWallClock(rule.clock_time) ?? "an unrecorded time"}`;
  }
  const meal = ANCHOR_LABELS[rule.anchor_type].toLowerCase();
  if (rule.anchor_relation === "with") return `With ${meal}`;
  return `${rule.offset_minutes} min ${rule.anchor_relation} ${meal}`;
}

/** The patient's recorded time for a meal anchor, if any. */
export function routineTimeFor(
  anchor: DoseAnchor | "",
  patient: PatientResponse | null | undefined,
): string | null {
  if (!patient || !anchor || anchor === "clock_time") return null;
  return patient[MEAL_FIELD[anchor]] ?? null;
}

/**
 * Why a course with dose rules would be refused by the schedule endpoint,
 * or null. Covers only the rule-specific preconditions; duration and
 * frequency are checked by the schedule panel's existing logic first. A
 * course with no rules returns null here and keeps its interval behaviour.
 */
export function ruleScheduleProblem(
  medication: MedicationResponse,
  patient: PatientResponse | null | undefined,
): string | null {
  const rules = medication.dose_rules;
  if (!rules || rules.length === 0) return null;

  if (medication.interval_hours != null) {
    return "Dose timings and an interval are both set. Clear one before scheduling.";
  }
  if (medication.times_per_day != null && rules.length !== medication.times_per_day) {
    return `${rules.length} of ${medication.times_per_day} dose timings set.`;
  }
  if (!patient) return null;
  if (!patient.timezone) {
    return "The patient's timezone is not recorded in their daily routine.";
  }
  const missing = Array.from(
    new Set(
      rules
        .filter((rule) => rule.anchor_type !== "clock_time" && !routineTimeFor(rule.anchor_type, patient))
        .map((rule) => ANCHOR_LABELS[rule.anchor_type]),
    ),
  );
  if (missing.length > 0) {
    return `${missing.join(" and ")} ${missing.length === 1 ? "time is" : "times are"} not recorded in the patient's daily routine.`;
  }
  return null;
}
