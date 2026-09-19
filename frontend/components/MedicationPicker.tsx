"use client";

import { useEffect, useId, useRef, useState } from "react";
import { StatusBanner } from "@/components/StatusBanner";
import { createMedication } from "@/lib/api/medications";
import { searchReferenceDrugs } from "@/lib/api/referenceDrugs";
import { ApiError } from "@/lib/api/errors";
import {
  REFERENCE_DRUG_MIN_QUERY_LENGTH,
  type MedicationResponse,
  type ReferenceDrugSearchResult,
} from "@/lib/api/types";
import { localCalendarDate } from "@/lib/dates/localDate";
import { rememberDrug } from "@/lib/drugs/nameCache";
import { medicationSearchSubtitle, termTypeLabel } from "@/lib/drugs/termType";
import { CheckIcon, SearchIcon } from "@/components/icons/Icons";
import { fieldOnCardClass } from "@/lib/ui/classes";

export function MedicationPicker({
  patientId,
  onCreated,
}: {
  patientId: string;
  onCreated: (medication: MedicationResponse) => void;
}) {
  const listId = useId();
  const inputId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const searchRequestRef = useRef(0);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ReferenceDrugSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ReferenceDrugSearchResult | null>(null);
  const [dose, setDose] = useState("");
  const [purpose, setPurpose] = useState("");
  const [startDate, setStartDate] = useState(() => localCalendarDate());
  const [duration, setDuration] = useState("");
  const [frequencyMode, setFrequencyMode] = useState<"" | "times_per_day" | "interval_hours">("");
  const [frequency, setFrequency] = useState("");
  const [durationTouched, setDurationTouched] = useState(false);
  const [frequencyTouched, setFrequencyTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    const q = query.trim();
    const requestId = ++searchRequestRef.current;

    if (q.length < REFERENCE_DRUG_MIN_QUERY_LENGTH) {
      setResults([]);
      setSearching(false);
      setSearchError(null);
      setOpen(false);
      setActiveIndex(-1);
      return;
    }
    if (selected && q === selected.name) {
      setSearching(false);
      return;
    }

    const handle = window.setTimeout(async () => {
      setSearching(true);
      setSearchError(null);
      try {
        const found = await searchReferenceDrugs(q);
        if (requestId !== searchRequestRef.current) return;
        setResults(found);
        setOpen(true);
        setActiveIndex(found.length > 0 ? 0 : -1);
      } catch (error) {
        if (requestId !== searchRequestRef.current) return;
        setResults([]);
        setOpen(false);
        setSearchError(error instanceof ApiError ? error.detail : "Catalog search failed.");
      } finally {
        if (requestId === searchRequestRef.current) setSearching(false);
      }
    }, 300);

    return () => window.clearTimeout(handle);
  }, [query, selected]);

  useEffect(() => {
    if (!open || activeIndex < 0 || !results[activeIndex]) return;
    const option = document.getElementById(`${listId}-opt-${results[activeIndex].id}`);
    option?.scrollIntoView?.({ block: "nearest" });
  }, [activeIndex, listId, open, results]);

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      if (open && rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
        setActiveIndex(-1);
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function selectDrug(drug: ReferenceDrugSearchResult) {
    setSelected(drug);
    setQuery(drug.name);
    setResults([]);
    setOpen(false);
    setActiveIndex(-1);
    rememberDrug(drug);
  }

  function onSearchKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      setActiveIndex(-1);
      return;
    }
    if (!open || results.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => (index <= 0 ? results.length - 1 : index - 1));
    } else if (event.key === "Enter" && activeIndex >= 0 && results[activeIndex]) {
      event.preventDefault();
      selectDrug(results[activeIndex]);
    }
  }

  const durationValue = Number(duration);
  const frequencyValue = Number(frequency);
  const validDuration = duration.trim() !== "" && Number.isSafeInteger(durationValue) && durationValue >= 1;
  const validFrequency = frequency.trim() !== "" && Number.isFinite(frequencyValue) && (
    frequencyMode === "times_per_day"
      ? Number.isInteger(frequencyValue) && frequencyValue >= 1 && frequencyValue <= 24
      : frequencyMode === "interval_hours" && frequencyValue > 0
  );

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!selected || submitting || !startDate || !validDuration || !validFrequency) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      rememberDrug(selected);
      const created = await createMedication(patientId, {
        drug_id: selected.id,
        start_date: startDate,
        status: "active",
        dose: dose.trim() || null,
        purpose_text: purpose.trim() || null,
        duration_days: durationValue,
        times_per_day: frequencyMode === "times_per_day" ? frequencyValue : null,
        interval_hours: frequencyMode === "interval_hours" ? frequencyValue : null,
      });
      onCreated(created);
      setSelected(null);
      setQuery("");
      setResults([]);
      setDose("");
      setPurpose("");
      setDuration("");
      setFrequencyMode("");
      setFrequency("");
      setDurationTouched(false);
      setFrequencyTouched(false);
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.detail : "Could not add medication.");
    } finally {
      setSubmitting(false);
    }
  }

  const activeOptionId = open && activeIndex >= 0 && results[activeIndex]
    ? `${listId}-opt-${results[activeIndex].id}`
    : undefined;

  return (
    <form onSubmit={handleSubmit} className="pv-meds-form">
      <div className="pv-meds-form-intro">
        <h2 className="pv-meds-form-title">What medication are you taking?</h2>
        <p className="pv-meds-form-hint">
          Search by the name on the strip or bottle. Brand names and ingredients can both be recognized.
        </p>
      </div>

      <div ref={rootRef} className="pv-meds-search">
        <div className="pv-meds-label-row">
          <label className="pv-meds-label" htmlFor={inputId}>Medicine name</label>
          <span className="pv-meds-catalog-tag">Verified catalog</span>
        </div>
        <div className="relative">
          <span aria-hidden="true" className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-3">
            <SearchIcon className="h-[1.05rem] w-[1.05rem]" />
          </span>
          <input
            id={inputId}
            type="text"
            role="combobox"
            autoComplete="off"
            value={query}
            onChange={(event) => { setQuery(event.target.value); setSelected(null); }}
            onKeyDown={onSearchKeyDown}
            placeholder="e.g. Vasograin, aspirin, metformin"
            className={`${fieldOnCardClass} pv-meds-field pl-10`}
            aria-expanded={open}
            aria-haspopup="listbox"
            aria-controls={open ? listId : undefined}
            aria-autocomplete="list"
            aria-activedescendant={activeOptionId}
          />
        </div>

        {searching ? <p className="pv-meds-search-status">Checking the medication catalog…</p> : null}
        {searchError ? <div className="mt-2"><StatusBanner tone="error" role="alert">{searchError}</StatusBanner></div> : null}
        {!searching && !searchError && query.trim().length >= REFERENCE_DRUG_MIN_QUERY_LENGTH && open && results.length === 0 ? (
          <div className="pv-meds-nomatch">
            <p className="pv-meds-nomatch-title">We couldn’t find a verified catalog match.</p>
            <p className="pv-meds-nomatch-text">Check the spelling or use the active ingredient printed on the package. We won’t guess a medication identity.</p>
          </div>
        ) : null}

        {open && results.length > 0 ? (
          <ul id={listId} role="listbox" className="pv-meds-options">
            {results.map((drug, index) => {
              const active = index === activeIndex;
              return (
                <li
                  key={drug.id}
                  id={`${listId}-opt-${drug.id}`}
                  role="option"
                  aria-selected={active}
                  onMouseEnter={() => setActiveIndex(index)}
                  onMouseDown={(event) => { event.preventDefault(); selectDrug(drug); }}
                  className={`pv-meds-option ${active ? "is-active" : ""}`}
                >
                  <div className="pv-meds-option-row">
                    <span className="pv-meds-option-name">{drug.name}</span>
                    <span className="pv-meds-option-code">
                      {drug.term_type || "match"}
                    </span>
                  </div>
                  <span className="pv-meds-option-sub">{medicationSearchSubtitle(drug)}</span>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>

      {selected ? (
        <div className="pv-meds-selected">
          <span className="pv-meds-selected-icon" aria-hidden="true">
            <CheckIcon className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <p className="pv-meds-selected-label">Medication selected</p>
            <p className="pv-meds-selected-name">
              <span className="pv-meds-selected-drug">{selected.name}</span>
              <span className="pv-meds-selected-kind">{termTypeLabel(selected.term_type)}</span>
            </p>
            {selected.rxcui ? <p className="pv-meds-selected-note">Standardized medication identity linked for safety analysis.</p> : null}
          </div>
        </div>
      ) : null}

      <div className="pv-meds-form-group">
        <p className="pv-meds-form-group-title">Prescription details</p>
        <div className="pv-meds-form-grid">
          <div>
            <label className="pv-meds-label" htmlFor="start-date">Start date</label>
            <input id="start-date" type="date" required value={startDate} onChange={(event) => setStartDate(event.target.value)} className={`${fieldOnCardClass} pv-meds-field`} />
          </div>
          <div>
            <label className="pv-meds-label" htmlFor="dose">Dose <span className="pv-meds-optional">(optional)</span></label>
            <input id="dose" value={dose} onChange={(event) => setDose(event.target.value)} placeholder="e.g. 1 tablet" className={`${fieldOnCardClass} pv-meds-field`} />
          </div>
          <div className="pv-meds-form-wide">
            <label className="pv-meds-label" htmlFor="purpose">Purpose <span className="pv-meds-optional">(optional)</span></label>
            <input id="purpose" value={purpose} onChange={(event) => setPurpose(event.target.value)} placeholder="e.g. Migraine" className={`${fieldOnCardClass} pv-meds-field`} />
          </div>
        </div>
      </div>

      <div className="pv-meds-form-group">
        <p className="pv-meds-form-group-title">Scheduling details</p>
        <div className="pv-meds-form-grid">
          <div className="pv-meds-form-wide">
            <label className="pv-meds-label" htmlFor="medication-duration">Duration (days)</label>
            <input
              id="medication-duration" type="number" inputMode="numeric" required min={1} step={1}
              value={duration} onChange={(event) => setDuration(event.target.value)}
              onBlur={() => setDurationTouched(true)}
              aria-invalid={(durationTouched || duration !== "") && !validDuration}
              aria-describedby="medication-duration-help"
              className={`${fieldOnCardClass} pv-meds-field`}
            />
            <p id="medication-duration-help" className="pv-meds-form-hint">Enter a whole number of days, at least 1.</p>
          </div>
          <div>
            <label className="pv-meds-label" htmlFor="medication-frequency-mode">Frequency mode</label>
            <select
              id="medication-frequency-mode" required value={frequencyMode}
              onChange={(event) => {
                setFrequencyMode(event.target.value as typeof frequencyMode);
                setFrequency("");
                setFrequencyTouched(false);
              }}
              className={`${fieldOnCardClass} pv-meds-field`}
            >
              <option value="">Choose mode</option>
              <option value="times_per_day">Times per day</option>
              <option value="interval_hours">Interval (hours)</option>
            </select>
          </div>
          <div>
            <label className="pv-meds-label" htmlFor="medication-frequency">
              {frequencyMode === "times_per_day" ? "Times per day" : frequencyMode === "interval_hours" ? "Hours between doses" : "Frequency value"}
            </label>
            <input
              id="medication-frequency" type="number" required disabled={!frequencyMode}
              inputMode={frequencyMode === "interval_hours" ? "decimal" : "numeric"}
              min={frequencyMode === "times_per_day" ? 1 : 0}
              max={frequencyMode === "times_per_day" ? 24 : undefined}
              step={frequencyMode === "times_per_day" ? 1 : "any"}
              value={frequency} onChange={(event) => setFrequency(event.target.value)}
              onBlur={() => setFrequencyTouched(true)}
              aria-invalid={(frequencyTouched || frequency !== "") && !validFrequency}
              aria-describedby="medication-frequency-help"
              className={`${fieldOnCardClass} pv-meds-field`}
            />
            <p id="medication-frequency-help" className="pv-meds-form-hint">
              {frequencyMode === "times_per_day" ? "Enter a whole number from 1 to 24." : frequencyMode === "interval_hours" ? "Enter hours greater than 0. Decimals are allowed." : "Choose how to enter the prescribed frequency."}
            </p>
          </div>
        </div>
        <p className="pv-meds-form-hint">Save the prescribed values here, then use Create schedule to generate doses.</p>
      </div>

      {submitError ? <StatusBanner tone="error" role="alert">{submitError}</StatusBanner> : null}
      <button type="submit" disabled={!selected || submitting || !startDate || !validDuration || !validFrequency} className="on-dark pv-meds-submit">
        {submitting ? "Adding medication…" : "Add medication"}
      </button>
    </form>
  );
}
