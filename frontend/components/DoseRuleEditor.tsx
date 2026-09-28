"use client";

import { useMemo, useState } from "react";
import { ApiError } from "@/lib/api/errors";
import { updateMedication } from "@/lib/api/medications";
import type { DoseAnchor, DoseRelation, MedicationResponse, PatientResponse } from "@/lib/api/types";
import { fieldOnSunkClass } from "@/lib/ui/classes";
import {
  ANCHOR_LABELS,
  MAX_OFFSET_MINUTES,
  RELATION_LABELS,
  draftFromResponse,
  draftsToPayload,
  emptyDraft,
  formatWallClock,
  routineTimeFor,
  ruleProblem,
  type DoseRuleDraft,
} from "@/lib/medications/doseRules";
import { StatusBanner } from "@/components/StatusBanner";

const ANCHORS: DoseAnchor[] = ["breakfast", "lunch", "dinner", "clock_time"];
const RELATIONS: DoseRelation[] = ["before", "with", "after"];

/**
 * Edits a medication's daily dose timing as one ordered collection.
 *
 * Saving replaces the whole set through PUT /medications/{id} and sends
 * nothing but `dose_rules`, so every other field of the course is left as
 * it was. It never generates a schedule: that stays the explicit Create
 * schedule action, and doses already created are not touched by a save.
 *
 * Rendered only when the parent has the medication's rules in hand; a
 * medication whose rules were not loaded must not reach here, or a save
 * could clear timing nobody meant to clear.
 */
export function DoseRuleEditor({
  medication,
  patient,
  onSaved,
  onCancel,
}: {
  medication: MedicationResponse & { dose_rules: NonNullable<MedicationResponse["dose_rules"]> };
  patient: PatientResponse | null;
  onSaved: (updated: MedicationResponse) => void;
  onCancel: () => void;
}) {
  const initial = useMemo(
    () => [...medication.dose_rules].sort((a, b) => a.sequence - b.sequence).map(draftFromResponse),
    [medication.dose_rules],
  );
  const [drafts, setDrafts] = useState<DoseRuleDraft[]>(initial);
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const limit = medication.times_per_day ?? 0;
  const problems = drafts.map(ruleProblem);
  const hasProblems = problems.some(Boolean);
  const originalPayload = useMemo(() => JSON.stringify(draftsToPayload(initial)), [initial]);
  const dirty = hasProblems || JSON.stringify(draftsToPayload(drafts)) !== originalPayload;
  const clearing = drafts.length === 0 && medication.dose_rules.length > 0;
  const idBase = `timing-${medication.id}`;

  function update(index: number, patch: Partial<DoseRuleDraft>) {
    setDrafts((current) => current.map((draft, i) => (i === index ? { ...draft, ...patch } : draft)));
  }

  // Changing what a dose is anchored to drops the fields that no longer
  // apply, so a stale offset can never ride along on a clock-time rule.
  function setAnchor(index: number, anchor: DoseAnchor | "") {
    update(index, anchor === "clock_time"
      ? { anchor, relation: "", offset: "" }
      : { anchor, clock: "" });
  }

  function setRelation(index: number, relation: DoseRelation | "") {
    update(index, relation === "with" || relation === "" ? { relation, offset: "" } : { relation });
  }

  function move(index: number, delta: -1 | 1) {
    setDrafts((current) => {
      const target = index + delta;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function save() {
    setAttempted(true);
    if (hasProblems || saving) return;
    setSaving(true);
    setError(null);
    try {
      onSaved(await updateMedication(medication.id, { dose_rules: draftsToPayload(drafts) }));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not save dose timing.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="pv-timing-editor">
      <p className="pv-meds-form-hint">
        Used when you create the schedule. Doses already created are not changed.
      </p>

      {drafts.length === 0 ? (
        <p className="pv-timing-empty">
          {clearing ? "All dose timings will be removed when you save." : "No dose timing set yet."}
        </p>
      ) : (
        <ol className="pv-timing-rules">
          {drafts.map((draft, index) => {
            const n = index + 1;
            const problem = problems[index];
            const fieldId = `${idBase}-${draft.key}`;
            const isMeal = draft.anchor !== "" && draft.anchor !== "clock_time";
            const needsOffset = isMeal && (draft.relation === "before" || draft.relation === "after");
            const routineTime = routineTimeFor(draft.anchor, patient);
            const routineMissing = isMeal && patient !== null && !routineTime;

            return (
              <li key={draft.key} className="pv-timing-rule">
                <div className="pv-timing-rule-head">
                  <p className="pv-timing-rule-title">Dose {n}</p>
                  <div className="pv-timing-rule-actions">
                    <button type="button" onClick={() => move(index, -1)} disabled={index === 0}
                      className="pv-timing-icon-button" aria-label={`Move dose ${n} earlier`}>
                      <span aria-hidden="true">↑</span>
                    </button>
                    <button type="button" onClick={() => move(index, 1)} disabled={index === drafts.length - 1}
                      className="pv-timing-icon-button" aria-label={`Move dose ${n} later`}>
                      <span aria-hidden="true">↓</span>
                    </button>
                    <button type="button"
                      onClick={() => setDrafts((current) => current.filter((_, i) => i !== index))}
                      className="pv-meds-quiet-button" aria-label={`Remove dose ${n}`}>
                      Remove
                    </button>
                  </div>
                </div>

                <div className="pv-timing-fields">
                  <div>
                    <label className="pv-meds-label" htmlFor={`${fieldId}-anchor`}>When</label>
                    <select id={`${fieldId}-anchor`} value={draft.anchor}
                      onChange={(event) => setAnchor(index, event.target.value as DoseAnchor | "")}
                      className={`${fieldOnSunkClass} pv-meds-field`}>
                      <option value="">Choose</option>
                      {ANCHORS.map((anchor) => {
                        const recorded = routineTimeFor(anchor, patient);
                        const suffix = anchor === "clock_time" || !patient
                          ? ""
                          : recorded ? ` · ${formatWallClock(recorded)}` : " · not recorded";
                        return <option key={anchor} value={anchor}>{ANCHOR_LABELS[anchor]}{suffix}</option>;
                      })}
                    </select>
                  </div>

                  {isMeal ? (
                    <div className={needsOffset ? "pv-timing-pair" : undefined}>
                      <div>
                        <label className="pv-meds-label" htmlFor={`${fieldId}-relation`}>Timing</label>
                        <select id={`${fieldId}-relation`} value={draft.relation}
                          onChange={(event) => setRelation(index, event.target.value as DoseRelation | "")}
                          className={`${fieldOnSunkClass} pv-meds-field`}>
                          <option value="">Choose</option>
                          {RELATIONS.map((relation) => (
                            <option key={relation} value={relation}>{RELATION_LABELS[relation]}</option>
                          ))}
                        </select>
                      </div>
                      {needsOffset ? (
                        <div>
                          <label className="pv-meds-label" htmlFor={`${fieldId}-offset`}>Minutes</label>
                          <input id={`${fieldId}-offset`} type="number" inputMode="numeric"
                            min={1} max={MAX_OFFSET_MINUTES} step={1} value={draft.offset}
                            onChange={(event) => update(index, { offset: event.target.value })}
                            aria-invalid={(attempted || draft.offset !== "") && problem !== null}
                            className={`${fieldOnSunkClass} pv-meds-field`} />
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  {draft.anchor === "clock_time" ? (
                    <div>
                      <label className="pv-meds-label" htmlFor={`${fieldId}-clock`}>Time</label>
                      <input id={`${fieldId}-clock`} type="time" value={draft.clock}
                        onChange={(event) => update(index, { clock: event.target.value })}
                        aria-invalid={attempted && problem !== null}
                        className={`${fieldOnSunkClass} pv-meds-field`} />
                    </div>
                  ) : null}

                  <div>
                    <label className="pv-meds-label" htmlFor={`${fieldId}-dose`}>
                      Amount <span className="pv-meds-optional">(optional)</span>
                    </label>
                    <input id={`${fieldId}-dose`} value={draft.dose} maxLength={200}
                      onChange={(event) => update(index, { dose: event.target.value })}
                      placeholder={medication.dose ? `Same as course: ${medication.dose}` : "Same as course dose"}
                      className={`${fieldOnSunkClass} pv-meds-field`} />
                  </div>
                </div>

                {routineMissing ? (
                  <p className="pv-timing-note">
                    {ANCHOR_LABELS[draft.anchor as DoseAnchor]} time isn&apos;t recorded in this patient&apos;s
                    daily routine. Record it before creating the schedule.
                  </p>
                ) : null}
                {attempted && problem ? (
                  <p className="pv-timing-problem" role="alert">Dose {n}: {problem}</p>
                ) : null}
              </li>
            );
          })}
        </ol>
      )}

      <div className="pv-timing-footer">
        <button type="button" onClick={() => setDrafts((current) => [...current, emptyDraft()])}
          disabled={drafts.length >= limit} className="pv-meds-quiet-button">
          Add dose timing
        </button>
        <p className="pv-timing-count">
          {drafts.length} of {limit} daily {limit === 1 ? "dose" : "doses"}
        </p>
      </div>

      {error ? <StatusBanner tone="error" role="alert">{error}</StatusBanner> : null}

      <div className="pv-timing-actions">
        <button type="button" onClick={() => void save()} disabled={saving || !dirty}
          className="on-dark pv-timing-save">
          {saving ? "Saving…" : clearing ? "Clear dose timing" : "Save dose timing"}
        </button>
        <button type="button" onClick={onCancel} disabled={saving} className="pv-meds-quiet-button pv-timing-cancel">
          Cancel
        </button>
      </div>
    </div>
  );
}
