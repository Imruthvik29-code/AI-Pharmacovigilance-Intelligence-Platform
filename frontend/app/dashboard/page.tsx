"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthGate } from "@/components/AuthGate";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { PatientForm } from "@/components/PatientForm";
import { StatusBanner } from "@/components/StatusBanner";
import { PatientAvatar } from "@/components/PatientAvatar";
import { ChevronRightIcon, PlusIcon } from "@/components/icons/Icons";
import { listPatients } from "@/lib/api/patients";
import { ApiError } from "@/lib/api/errors";
import { clearSession, loadSession } from "@/lib/auth/session";
import { usePageTitle } from "@/lib/hooks/usePageTitle";
import { demographicLine } from "@/lib/patient/summaries";
import { ghostButtonClass } from "@/lib/ui/classes";
import type { PatientResponse } from "@/lib/api/types";

/**
 * The roster, in the reference's first-frame language: a greeting block, a
 * section title with its count, and compact identity rows on the same cool
 * canvas, the same card radius and the same elevation as the patient screens.
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

  return (
    <AuthGate>
      <div className="pv-canvas min-h-screen px-4 pb-16 pt-8 sm:px-6">
        <header className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-[1.75rem] font-bold leading-tight tracking-[-0.025em] sm:text-[2.125rem]">
              Patients
            </h1>
            <p className="mt-1 text-[0.9375rem] text-ink-2">
              Choose a record to review
            </p>
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
              <PlusIcon
                className={`h-5 w-5 transition-transform ${showForm ? "rotate-45" : ""}`}
              />
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

        <div className="mt-8">
          <div className="mb-3.5 flex items-end justify-between gap-4">
            <h2 className="pv-section-title">Recent patients</h2>
            <span className="text-[0.875rem] font-medium text-ink-3">
              {patients.length} {patients.length === 1 ? "record" : "records"}
            </span>
          </div>

          {loading ? (
            <div className="max-w-md">
              <LoadingSkeleton label="Loading patients" lines={4} />
            </div>
          ) : null}

          {error ? (
            <StatusBanner tone="error" role="alert">
              {error}
            </StatusBanner>
          ) : null}

          {!loading && !error && patients.length === 0 ? (
            <section className="rounded-card bg-surface px-6 py-12 text-center shadow-[var(--e-row)]">
              <h2 className="pv-section-title">No patients yet</h2>
              <p className="mx-auto mt-2 max-w-sm text-[0.875rem] leading-6 text-ink-2">
                Add a patient to start a medication record and run safety analysis.
              </p>
            </section>
          ) : null}

          {!loading && patients.length > 0 ? (
            <ul className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
              {patients.map((patient) => (
                <li key={patient.id}>
                  <button
                    type="button"
                    onClick={() => router.push(`/patients/${patient.id}`)}
                    className="pv-roster-card"
                  >
                    <PatientAvatar patient={patient} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[1.125rem] font-bold tracking-[-0.015em]">
                        {patient.name}
                      </span>
                      <span className="mt-1 block truncate text-[0.875rem] text-ink-3">
                        {demographicLine(patient)}
                      </span>
                    </span>
                    <span className="pv-chevron" aria-hidden="true">
                      <ChevronRightIcon className="h-[1.125rem] w-[1.125rem]" />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </AuthGate>
  );
}
