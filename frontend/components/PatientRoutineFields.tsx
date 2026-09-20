"use client";

import type { PatientRoutine } from "@/lib/api/types";
import { fieldClass } from "@/lib/ui/classes";

export type RoutineDraft = {
  timezone: string;
  breakfast: string;
  lunch: string;
  dinner: string;
};

export const EMPTY_ROUTINE: RoutineDraft = { timezone: "", breakfast: "", lunch: "", dinner: "" };

/**
 * The browser's IANA zone, used only to prefill a field the user can still
 * change. It is the device's zone, which is not necessarily the patient's --
 * a caregiver may be in another country -- so it is never submitted without
 * being shown first.
 */
export function detectTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone ?? "";
  } catch {
    return "";
  }
}

/** "HH:MM" / "HH:MM:SS" from the API -> the "HH:MM" an input[type=time] wants. */
export function toTimeInputValue(value: string | null | undefined): string {
  if (!value) return "";
  const match = /^(\d{2}):(\d{2})/.exec(value);
  return match ? `${match[1]}:${match[2]}` : "";
}

/** Blank stays null: an unrecorded meal time is never guessed at. */
function orNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

export function routineToPayload(draft: RoutineDraft): PatientRoutine {
  return {
    timezone: orNull(draft.timezone),
    breakfast_time: orNull(draft.breakfast),
    lunch_time: orNull(draft.lunch),
    dinner_time: orNull(draft.dinner),
  };
}

const MEALS: Array<{ key: keyof Omit<RoutineDraft, "timezone">; label: string }> = [
  { key: "breakfast", label: "Breakfast" },
  { key: "lunch", label: "Lunch" },
  { key: "dinner", label: "Dinner" },
];

/**
 * Patient routine capture, shared by the create and edit surfaces. Every
 * field is optional and purely contextual -- this records when the patient
 * usually eats, never how or when to take a medicine.
 */
export function PatientRoutineFields({
  value,
  onChange,
  idPrefix = "routine",
}: {
  value: RoutineDraft;
  onChange: (next: RoutineDraft) => void;
  /** Keeps ids unique if both surfaces ever mount together. */
  idPrefix?: string;
}) {
  function set<K extends keyof RoutineDraft>(key: K, next: string) {
    onChange({ ...value, [key]: next });
  }

  return (
    <fieldset className="space-y-3 border-0 p-0">
      <legend className="text-sm font-medium">
        Daily routine <span className="font-normal text-ink-2">(optional)</span>
      </legend>
      <p className="text-[0.8125rem] leading-snug text-ink-2">
        The patient&apos;s usual mealtimes. This is routine context used to work out sensible dose
        times later — it is not a medication instruction.
      </p>

      <div>
        <label className="block text-sm font-medium" htmlFor={`${idPrefix}-timezone`}>
          Timezone
        </label>
        <input
          id={`${idPrefix}-timezone`}
          value={value.timezone}
          onChange={(event) => set("timezone", event.target.value)}
          placeholder="e.g. Asia/Kolkata"
          aria-describedby={`${idPrefix}-timezone-help`}
          className={fieldClass}
        />
        <p id={`${idPrefix}-timezone-help`} className="mt-1 text-[0.75rem] text-ink-3">
          Detected from this device. Change it if the patient is elsewhere.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {MEALS.map((meal) => (
          <div key={meal.key}>
            <label className="block text-sm font-medium" htmlFor={`${idPrefix}-${meal.key}`}>
              {meal.label}
            </label>
            <input
              id={`${idPrefix}-${meal.key}`}
              type="time"
              value={value[meal.key]}
              onChange={(event) => set(meal.key, event.target.value)}
              className={fieldClass}
            />
          </div>
        ))}
      </div>
    </fieldset>
  );
}
