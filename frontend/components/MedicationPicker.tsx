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
import { fieldClass, primaryButtonClass } from "@/lib/ui/classes";

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

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!selected || submitting) return;
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
      });
      onCreated(created);
      setSelected(null);
      setQuery("");
      setResults([]);
      setDose("");
      setPurpose("");
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
    <form onSubmit={handleSubmit} className="rounded-3xl border border-line bg-card p-5 shadow-sm sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Medication identity</p>
          <h2 className="mt-1 text-lg font-semibold tracking-tight">What medication are you taking?</h2>
          <p className="mt-1 max-w-xl text-sm text-muted">
            Search by the name on the strip or bottle. Brand names and ingredients can both be recognized.
          </p>
        </div>
        <span className="hidden rounded-full bg-paper px-3 py-1 text-xs font-medium text-muted sm:inline-flex">Verified catalog</span>
      </div>

      <div ref={rootRef} className="relative mt-5">
        <label className="block text-sm font-medium" htmlFor={inputId}>Medicine name</label>
        <div className="relative mt-2">
          <span aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">⌕</span>
          <input
            id={inputId}
            type="text"
            role="combobox"
            autoComplete="off"
            value={query}
            onChange={(event) => { setQuery(event.target.value); setSelected(null); }}
            onKeyDown={onSearchKeyDown}
            placeholder="e.g. Vasograin, aspirin, metformin"
            className={`${fieldClass} pl-9`}
            aria-expanded={open}
            aria-haspopup="listbox"
            aria-controls={open ? listId : undefined}
            aria-autocomplete="list"
            aria-activedescendant={activeOptionId}
          />
        </div>

        {searching ? <p className="mt-2 text-sm text-muted">Checking the medication catalog…</p> : null}
        {searchError ? <div className="mt-2"><StatusBanner tone="error" role="alert">{searchError}</StatusBanner></div> : null}
        {!searching && !searchError && query.trim().length >= REFERENCE_DRUG_MIN_QUERY_LENGTH && open && results.length === 0 ? (
          <div className="mt-3 rounded-xl border border-dashed border-line bg-paper p-4">
            <p className="text-sm font-medium">We couldn’t find a verified catalog match.</p>
            <p className="mt-1 text-xs leading-5 text-muted">Check the spelling or use the active ingredient printed on the package. We won’t guess a medication identity.</p>
          </div>
        ) : null}

        {open && results.length > 0 ? (
          <ul id={listId} role="listbox" className="mt-2 max-h-72 overflow-auto rounded-2xl border border-line bg-card p-1 shadow-lg">
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
                  className={`cursor-pointer rounded-xl px-3 py-3 ${active ? "bg-paper" : "hover:bg-paper/70"}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-semibold">{drug.name}</span>
                    <span className="rounded-full bg-paper px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
                      {drug.term_type || "match"}
                    </span>
                  </div>
                  <span className="mt-1 block text-xs text-muted">{medicationSearchSubtitle(drug)}</span>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>

      {selected ? (
        <div className="mt-4 rounded-2xl border border-accent/20 bg-[#edf7f5] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">Medication selected</p>
          <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="text-base font-semibold">{selected.name}</span>
            <span className="text-sm text-muted">{termTypeLabel(selected.term_type)}</span>
          </div>
          {selected.rxcui ? <p className="mt-1 text-xs text-muted">Standardized medication identity linked for safety analysis.</p> : null}
        </div>
      ) : null}

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <div>
          <label className="block text-sm font-medium" htmlFor="start-date">Start date</label>
          <input id="start-date" type="date" required value={startDate} onChange={(event) => setStartDate(event.target.value)} className={fieldClass} />
        </div>
        <div>
          <label className="block text-sm font-medium" htmlFor="dose">Dose <span className="font-normal text-muted">(optional)</span></label>
          <input id="dose" value={dose} onChange={(event) => setDose(event.target.value)} placeholder="e.g. 1 tablet" className={fieldClass} />
        </div>
      </div>

      <label className="mt-3 block text-sm font-medium" htmlFor="purpose">Purpose <span className="font-normal text-muted">(optional)</span></label>
      <input id="purpose" value={purpose} onChange={(event) => setPurpose(event.target.value)} placeholder="e.g. Migraine" className={fieldClass} />

      {submitError ? <div className="mt-3"><StatusBanner tone="error" role="alert">{submitError}</StatusBanner></div> : null}
      <button type="submit" disabled={!selected || submitting} className={`${primaryButtonClass} mt-5 w-full sm:w-auto`}>
        {submitting ? "Adding medication…" : "Add medication"}
      </button>
    </form>
  );
}
