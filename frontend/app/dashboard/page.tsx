"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthGate } from "@/components/AuthGate";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { PatientForm } from "@/components/PatientForm";
import { StatusBanner } from "@/components/StatusBanner";
import { patientInitials } from "@/components/PatientAvatar";
import { ArrowRightIcon, ChevronRightIcon, PlusIcon } from "@/components/icons/Icons";
import { CATEGORIES } from "@/components/patient/categories";
import { listPatients } from "@/lib/api/patients";
import { ApiError } from "@/lib/api/errors";
import { clearSession, loadSession } from "@/lib/auth/session";
import { usePageTitle } from "@/lib/hooks/usePageTitle";
import { ghostButtonClass } from "@/lib/ui/classes";
import type { PatientResponse } from "@/lib/api/types";

/**
 * Patients directory.
 *
 * Identity-led rather than list-led: the most recent record leads as a card on
 * the identity surface, the rest follow as identity cards, and the whole
 * screen shares the card language of the patient screens. Desktop splits into
 * two editorial columns rather than centring the mobile column.
 *
 * Everything shown comes from `listPatients()` — name, age, sex and relation.
 * Initials only; no photo, no derived metric, no fabricated detail.
 */

/** Age and sex, omitting whatever the record does not carry. */
function demographics(patient: PatientResponse): string {
  const parts = [patient.age != null ? `${patient.age} yrs` : null, patient.sex].filter(Boolean);
  return parts.join(" · ");
}

/** Relation in the supported vocabulary; "Self" reads naturally as a label. */
function relationLabel(patient: PatientResponse): string | null {
  if (!patient.relation) return null;
  return patient.relation === "Self" ? "My profile" : patient.relation;
}

export default function DashboardPage() {
  usePageTitle("Patients");
  const router = useRouter();
  const [patients, setPatients] = useState<PatientResponse[]>([]);
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    setEmail(loadSession()?.user.email ?? null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const rows = await listPatients();
        if (!cancelled) setPatients(rows);
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 401) {
            router.replace("/login");
            return;
          }
          setError(err instanceof ApiError ? err.detail : "Could not load patients.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [router]);

  function signOut() {
    clearSession();
    router.replace("/login");
  }

  const [lead, ...rest] = patients;
  const leadRelation = lead ? relationLabel(lead) : null;

  return (
    <AuthGate>
      <div className="pv-directory min-h-screen">
        <header className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-4xl font-bold tracking-[-0.03em]">Patients</h1>
            <p className="mt-1.5 text-base text-ink-2">Choose a record to review</p>
            {email ? (
              <p className="mt-0.5 hidden truncate text-sm text-ink-3 sm:block">{email}</p>
            ) : null}
          </div>
          <div className="flex flex-none items-center gap-2">
            <button type="button" onClick={signOut} className={ghostButtonClass}>
              Sign out
            </button>
            <button
              type="button"
              aria-label={showForm ? "Close patient form" : "Add patient"}
              onClick={() => setShowForm((open) => !open)}
              className="on-dark inline-flex h-12 w-12 flex-none items-center justify-center rounded-full bg-cta text-white shadow-[var(--e-cta)] transition hover:-translate-y-0.5"
            >
              <PlusIcon className={`h-5 w-5 transition-transform ${showForm ? "rotate-45" : ""}`} />
            </button>
          </div>
        </header>

        {showForm ? (
          <div className="mt-6 max-w-xl rounded-card bg-surface p-5 shadow-[var(--e-panel)] sm:p-6">
            <h2 className="pv-section-title">New patient</h2>
            <p className="mt-1 text-base text-ink-2">
              Create a record to start tracking treatment and safety.
            </p>
            <div className="mt-5">
              <PatientForm onCreated={(patient) => router.push(`/patients/${patient.id}`)} />
            </div>
          </div>
        ) : null}

        {loading ? (
          <div className="mt-9 max-w-md">
            <LoadingSkeleton label="Loading patients" lines={4} />
          </div>
        ) : null}

        {error ? (
          <div className="mt-9">
            <StatusBanner tone="error" role="alert">
              {error}
            </StatusBanner>
          </div>
        ) : null}

        {!loading && !error && patients.length === 0 ? (
          <section className="mt-9 rounded-card bg-surface px-6 py-14 text-center shadow-[var(--e-row)]">
            <h2 className="pv-section-title">No patients yet</h2>
            <p className="mx-auto mt-2 max-w-sm text-base leading-6 text-ink-2">
              Add a patient to start a medication record and run safety analysis.
            </p>
          </section>
        ) : null}

        {lead ? (
          <div className="pv-directory-body mt-8">
            <section aria-label="Most recent patient">
              <div className="pv-lead-stage">
                <div className="pv-lead-peeks" aria-hidden="true">
                  {CATEGORIES.slice(1, 3).map((category) => (
                    <span
                      key={category.id}
                      className="pv-lead-peek"
                      style={{ backgroundColor: category.surface }}
                    />
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => router.push(`/patients/${lead.id}`)}
                  className="pv-lead on-dark"
                >
                  <span
                    aria-hidden="true"
                    className="pv-initials h-14 w-14 text-lg sm:h-16 sm:w-16 sm:text-xl"
                  >
                    {patientInitials(lead.name)}
                  </span>
                  <span className="mt-auto pt-6">
                    {leadRelation ? (
                      <span className="pv-relation pv-relation-on-dark mb-2.5">{leadRelation}</span>
                    ) : null}
                    <span className="pv-lead-name block">{lead.name}</span>
                    <span className="pv-lead-meta block">{demographics(lead)}</span>
                  </span>
                  <span className="pv-cta pv-cta-invert mt-5" aria-hidden="true">
                    <span className="truncate">View patient</span>
                    <span className="pv-cta-badge">
                      <ArrowRightIcon className="h-5 w-5" />
                    </span>
                  </span>
                </button>
              </div>
            </section>

            <section className="mt-9 lg:mt-0">
              <div className="mb-4 flex items-end justify-between gap-4">
                <h2 className="pv-section-title">
                  {rest.length > 0 ? "Other patients" : "Your records"}
                </h2>
                <span className="text-sm font-medium text-ink-3">
                  {patients.length} {patients.length === 1 ? "record" : "records"}
                </span>
              </div>

              {rest.length > 0 ? (
                <ul className="pv-roster-grid space-y-3 lg:space-y-0">
                  {rest.map((patient) => {
                    const relation = relationLabel(patient);
                    return (
                      <li key={patient.id}>
                        <button
                          type="button"
                          onClick={() => router.push(`/patients/${patient.id}`)}
                          className="pv-roster-item"
                        >
                          <span
                            aria-hidden="true"
                            className="pv-identity-chip h-12 w-12 flex-none text-base"
                          >
                            {patientInitials(patient.name)}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="pv-roster-name truncate">{patient.name}</span>
                            <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                              <span className="truncate text-sm text-ink-3">
                                {demographics(patient)}
                              </span>
                              {relation ? <span className="pv-relation">{relation}</span> : null}
                            </span>
                          </span>
                          <span className="pv-chevron" aria-hidden="true">
                            <ChevronRightIcon className="h-[1.125rem] w-[1.125rem]" />
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="rounded-card bg-surface px-5 py-6 text-base leading-6 text-ink-2 shadow-[var(--e-row)]">
                  This is your only record so far. Add another with the button above.
                </p>
              )}
            </section>
          </div>
        ) : null}
      </div>
    </AuthGate>
  );
}
