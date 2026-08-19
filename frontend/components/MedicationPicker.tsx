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
    if (q.length < REFERENCE_DRUG_MIN_QUERY_LENGTH) {
      setResults([]);
      setSearching(false);
      setSearchError(null);
      setOpen(false);
      setActiveIndex(-1);
      return;
    }
    if (selected && q === selected.name) {
      return;
    }

    const handle = window.setTimeout(async () => {
      setSearching(true);
      setSearchError(null);
      try {
        const found = await searchReferenceDrugs(q);
        setResults(found);
        setOpen(true);
        setActiveIndex(found.length > 0 ? 0 : -1);
      } catch (error) {
        setResults([]);
        setOpen(false);
        setSearchError(error instanceof ApiError ? error.detail : "Catalog search failed.");
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => window.clearTimeout(handle);
  }, [query, selected]);

  useEffect(() => {
    if (!open || activeIndex < 0 || !results[activeIndex]) return;
    const option = document.getElementById(`${listId}-opt-${results[activeIndex].id}`);
    if (option && typeof option.scrollIntoView === "function") {
      option.scrollIntoView({ block: "nearest" });
    }
  }, [activeIndex, listId, open, results]);

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      if (!open) return;
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
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

  const activeOptionId =
    open && activeIndex >= 0 && results[activeIndex]
      ? `${listId}-opt-${results[activeIndex].id}`
      : undefined;

  return (
    <form onSubmit={handleSubmit} className="rounded-2xl border border-line bg-card p-5">
      <h2 className="text-sm font-semibold">Add medication</h2>
      <p className="mt-1 text-xs text-muted">
        Search the reference catalog (at least {REFERENCE_DRUG_MIN_QUERY_LENGTH} characters).
      </p>

      <div ref={rootRef} className="relative mt-4">
        <label className="block text-sm font-medium" htmlFor={inputId}>
          Medication
        </label>
        <input
          id={inputId}
          type="text"
          role="combobox"
          autoComplete="off"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setSelected(null);
          }}
          onKeyDown={onSearchKeyDown}
          placeholder="Search by drug name"
          className={fieldClass}
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-controls={open ? listId : undefined}
          aria-autocomplete="list"
          aria-activedescendant={activeOptionId}
        />

        {searching ? <p className="mt-2 text-sm text-muted">Searching catalog…</p> : null}
        {searchError ? (
          <div className="mt-2">
            <StatusBanner tone="error" role="alert">
              {searchError}
            </StatusBanner>
          </div>
        ) : null}
        {!searching &&
        !searchError &&
        query.trim().length >= REFERENCE_DRUG_MIN_QUERY_LENGTH &&
        open &&
        results.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No catalog matches.</p>
        ) : null}

        {open && results.length > 0 ? (
          <ul
            id={listId}
            role="listbox"
            className="mt-2 max-h-64 overflow-auto rounded-lg border border-line bg-card"
          >
            {results.map((drug, index) => {
              const active = index === activeIndex;
              return (
                <li
                  key={drug.id}
                  id={`${listId}-opt-${drug.id}`}
                  role="option"
                  aria-selected={active}
                  onMouseEnter={() => setActiveIndex(index)}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    selectDrug(drug);
                  }}
                  className={`flex min-h-11 cursor-pointer flex-col items-start justify-center gap-0.5 px-3 py-2.5 ${
                    active ? "bg-[#e7f2f0]" : "hover:bg-paper"
                  }`}
                >
                  <span className="text-sm font-medium">{drug.name}</span>
                  <span className="text-xs text-muted">
                    {[drug.term_type, drug.source].filter(Boolean).join(" · ") || "Catalog match"}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>

      {selected ? (
        <p className="mt-2 text-sm">
          Selected <span className="font-medium">{selected.name}</span>
          {selected.term_type ? <span className="text-muted"> · {selected.term_type}</span> : null}
        </p>
      ) : null}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div>
          <label className="block text-sm font-medium" htmlFor="start-date">
            Start date
          </label>
          <input
            id="start-date"
            type="date"
            required
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
            className={fieldClass}
          />
        </div>
        <div>
          <label className="block text-sm font-medium" htmlFor="dose">
            Dose <span className="font-normal text-muted">(optional)</span>
          </label>
          <input
            id="dose"
            value={dose}
            onChange={(event) => setDose(event.target.value)}
            className={fieldClass}
          />
        </div>
      </div>

      <label className="mt-3 block text-sm font-medium" htmlFor="purpose">
        Purpose <span className="font-normal text-muted">(optional)</span>
      </label>
      <input
        id="purpose"
        value={purpose}
        onChange={(event) => setPurpose(event.target.value)}
        className={fieldClass}
      />

      {submitError ? (
        <div className="mt-3">
          <StatusBanner tone="error" role="alert">
            {submitError}
          </StatusBanner>
        </div>
      ) : null}

      <button
        type="submit"
        disabled={!selected || submitting}
        className={`${primaryButtonClass} mt-4`}
      >
        {submitting ? "Adding…" : "Add medication"}
      </button>
    </form>
  );
}
