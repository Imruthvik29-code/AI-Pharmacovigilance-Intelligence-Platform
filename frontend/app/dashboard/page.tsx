"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthGate } from "@/components/AuthGate";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { PatientForm } from "@/components/PatientForm";
import { StatusBanner } from "@/components/StatusBanner";
import { patientInitials } from "@/components/PatientAvatar";
import { ArrowRightIcon, PlusIcon } from "@/components/icons/Icons";
import { CATEGORIES } from "@/components/patient/categories";
import { listPatients } from "@/lib/api/patients";
import { ApiError } from "@/lib/api/errors";
import { clearSession, loadSession } from "@/lib/auth/session";
import { usePageTitle } from "@/lib/hooks/usePageTitle";
import { demographicLine } from "@/lib/patient/summaries";
import { ghostButtonClass } from "@/lib/ui/classes";
import type { PatientResponse } from "@/lib/api/types";

/**
 * The roster, composed as the calm first frame of the same product whose
 * second frame is the layered patient overview.
 *
 * The most recent record leads as a layered card on the identity surface with
 * the category tints standing behind its right edge — the overview's own
 * composition. The remaining records follow as compact identity chips. Same
 * data, same destination, same design system; only the hierarchy differs.
 */
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

  return (
    <AuthGate>
      <div className="pv-canvas min-h-screen px-4 pb-16 pt-8 sm:px-6">
        <header className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-[1.75rem] font-bold leading-tight tracking-[-0.025em] sm:text-[2.125rem]">
              Patients
            </h1>
            <p className="mt-1 text-[0.9375rem] text-ink-2">Choose a record to review</p>
            {email ? (
              <p className="mt-0.5 hidden truncate text-[0.8125rem] text-ink-3 sm:block">{email}</p>
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
          <div className="mt-6 max-w-xl rounded-card bg-surface p-5 shadow-[var(--e-float)] sm:p-6">
            <h2 className="pv-section-title">New patient</h2>
            <p className="mt-1 text-[0.875rem] text-ink-2">
              Create a record to start tracking treatment and safety.
            </p>
            <div className="mt-5">
              <PatientForm onCreated={(patient) => router.push(`/patients/${patient.id}`)} />
            </div>
          </div>
        ) : null}

        {loading ? (
          <div className="mt-8 max-w-md">
            <LoadingSkeleton label="Loading patients" lines={4} />
          </div>
        ) : null}

        {error ? (
          <div className="mt-8">
            <StatusBanner tone="error" role="alert">
              {error}
            </StatusBanner>
          </div>
        ) : null}

        {!loading && !error && patients.length === 0 ? (
          <section className="mt-8 rounded-card bg-surface px-6 py-12 text-center shadow-[var(--e-row)]">
            <h2 className="pv-section-title">No patients yet</h2>
            <p className="mx-auto mt-2 max-w-sm text-[0.875rem] leading-6 text-ink-2">
              Add a patient to start a medication record and run safety analysis.
            </p>
          </section>
        ) : null}

        {lead ? (
          <section className="mt-7" aria-label="Most recent patient">
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
                  className="pv-initials h-12 w-12 text-base sm:h-14 sm:w-14 sm:text-lg"
                >
                  {patientInitials(lead.name)}
                </span>
                <span className="mt-auto pt-6">
                  <span className="pv-lead-name block">{lead.name}</span>
                  <span className="pv-lead-meta block">{demographicLine(lead)}</span>
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
        ) : null}

        {rest.length > 0 ? (
          <section className="mt-9">
            <div className="mb-3.5 flex items-end justify-between gap-4">
              <h2 className="pv-section-title">Recent patients</h2>
              <span className="text-[0.875rem] font-medium text-ink-3">
                {patients.length} {patients.length === 1 ? "record" : "records"}
              </span>
            </div>
            <ul className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(11.5rem,1fr))]">
              {rest.map((patient) => (
                <li key={patient.id}>
                  <button
                    type="button"
                    onClick={() => router.push(`/patients/${patient.id}`)}
                    className="pv-chip-card"
                  >
                    <span
                      aria-hidden="true"
                      className="pv-identity-chip h-11 w-11 text-[0.8125rem]"
                    >
                      {patientInitials(patient.name)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[0.9375rem] font-bold tracking-[-0.015em]">
                        {patient.name}
                      </span>
                      <span className="mt-0.5 block truncate text-[0.8125rem] text-ink-3">
                        {demographicLine(patient)}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </AuthGate>
  );
}
