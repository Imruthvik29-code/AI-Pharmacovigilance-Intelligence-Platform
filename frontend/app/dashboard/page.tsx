"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { PatientForm } from "@/components/PatientForm";
import { StatusBanner } from "@/components/StatusBanner";
import { listPatients } from "@/lib/api/patients";
import { ApiError } from "@/lib/api/errors";
import { usePageTitle } from "@/lib/hooks/usePageTitle";
import { primaryButtonClass } from "@/lib/ui/classes";
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
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-accent">
              Workspace
            </p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight">Patients</h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-muted">
              Create a patient, add catalog medications, then run a deterministic safety analysis.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowForm((open) => !open)}
            className={primaryButtonClass}
          >
            {showForm ? "Close" : "Add patient"}
          </button>
        </div>

        {showForm ? (
          <div className="mt-6 max-w-lg rounded-2xl border border-line bg-card p-5">
            <h2 className="text-sm font-semibold">New patient</h2>
            <div className="mt-4">
              <PatientForm
                onCreated={(patient) => {
                  router.push(`/patients/${patient.id}`);
                }}
              />
            </div>
          </div>
        ) : null}

        <div className="mt-8">
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
            <section className="rounded-2xl border border-dashed border-line bg-card px-5 py-8">
              <h2 className="text-sm font-semibold">No patients yet</h2>
              <p className="mt-2 max-w-lg text-sm leading-6 text-muted">
                Add a patient to start a medication record and run safety analysis.
              </p>
            </section>
          ) : null}
          {!loading && patients.length > 0 ? (
            <ul className="grid gap-3 sm:grid-cols-2">
              {patients.map((patient) => (
                <li key={patient.id}>
                  <button
                    type="button"
                    onClick={() => router.push(`/patients/${patient.id}`)}
                    className="min-h-20 w-full rounded-2xl border border-line bg-card px-4 py-4 text-left hover:border-accent"
                  >
                    <p className="font-medium">{patient.name}</p>
                    <p className="mt-1 text-sm text-muted">
                      {[patient.age != null ? `Age ${patient.age}` : null, patient.sex]
                        .filter(Boolean)
                        .join(" · ") || "No demographics recorded"}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </AppShell>
    </AuthGate>
  );
}
