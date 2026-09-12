"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { PatientForm } from "@/components/PatientForm";
import { StatusBanner } from "@/components/StatusBanner";
import { PatientAvatar } from "@/components/PatientAvatar";
import { ArrowRightIcon, PlusIcon } from "@/components/icons/Icons";
import { listPatients } from "@/lib/api/patients";
import { ApiError } from "@/lib/api/errors";
import { usePageTitle } from "@/lib/hooks/usePageTitle";
import { demographicLine } from "@/lib/patient/summaries";
import type { PatientResponse } from "@/lib/api/types";

export default function DashboardPage() {
  usePageTitle("Dashboard");
  const router = useRouter();
  const [patients, setPatients] = useState<PatientResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

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

  return (
    <AuthGate>
      <AppShell>
        <section className="pt-4 sm:pt-8">
          <header className="flex items-start justify-between gap-4 px-1">
            <div>
              <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-ink-3">
                Your clinical records
              </p>
              <h1 className="mt-2 text-[2.125rem] font-semibold tracking-[-0.02em] sm:text-[2.75rem]">
                Patients
              </h1>
              <p className="mt-2 max-w-md text-[0.875rem] leading-6 text-ink-2">
                Choose a patient to review treatment, reported symptoms, and deterministic safety
                findings.
              </p>
            </div>
            <button
              type="button"
              aria-label={showForm ? "Close patient form" : "Add patient"}
              onClick={() => setShowForm((open) => !open)}
              className="on-dark inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-identity-deep text-white shadow-[var(--e2)] transition hover:-translate-y-0.5"
            >
              <PlusIcon className={`h-5 w-5 transition-transform ${showForm ? "rotate-45" : ""}`} />
            </button>
          </header>

          {showForm ? (
            <div className="mt-6 max-w-xl rounded-xl bg-surface p-5 shadow-[var(--e2)] sm:p-7">
              <h2 className="text-[1.25rem] font-semibold tracking-[-0.015em]">New patient</h2>
              <p className="mt-1 text-[0.875rem] text-ink-2">
                Create a record to start tracking treatment and safety.
              </p>
              <div className="mt-5">
                <PatientForm onCreated={(patient) => router.push(`/patients/${patient.id}`)} />
              </div>
            </div>
          ) : null}

          <div className="mt-9">
            <div className="mb-4 flex items-end justify-between gap-4 px-1">
              <h2 className="text-[1.125rem] font-semibold tracking-[-0.015em]">Recent patients</h2>
              <span className="text-[0.8125rem] text-ink-3">{patients.length} records</span>
            </div>

            {loading ? (
              <div className="max-w-md px-1">
                <LoadingSkeleton label="Loading patients" lines={4} />
              </div>
            ) : null}

            {error ? (
              <StatusBanner tone="error" role="alert">
                {error}
              </StatusBanner>
            ) : null}

            {!loading && !error && patients.length === 0 ? (
              <section className="rounded-xl bg-surface px-6 py-12 text-center shadow-[var(--e1)]">
                <h2 className="text-[1.0625rem] font-semibold">No patients yet</h2>
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
                      className="flex min-h-32 w-full items-center gap-4 rounded-xl bg-surface p-5 text-left shadow-[var(--e2)] transition hover:-translate-y-1"
                    >
                      <PatientAvatar patient={patient} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[1.125rem] font-semibold tracking-[-0.015em]">
                          {patient.name}
                        </span>
                        <span className="mt-1 block text-[0.8125rem] text-ink-2">
                          {demographicLine(patient)}
                        </span>
                      </span>
                      <span
                        className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-surface-sunk text-ink"
                        aria-hidden="true"
                      >
                        <ArrowRightIcon className="h-5 w-5" />
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </section>
      </AppShell>
    </AuthGate>
  );
}
