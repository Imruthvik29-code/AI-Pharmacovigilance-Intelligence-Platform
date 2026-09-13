"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthGate } from "@/components/AuthGate";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { PatientForm } from "@/components/PatientForm";
import { StatusBanner } from "@/components/StatusBanner";
import { PatientDeck } from "@/components/patient/PatientDeck";
import { PlusIcon } from "@/components/icons/Icons";
import { listPatients } from "@/lib/api/patients";
import { ApiError } from "@/lib/api/errors";
import { clearSession, loadSession } from "@/lib/auth/session";
import { usePageTitle } from "@/lib/hooks/usePageTitle";
import { ghostButtonClass } from "@/lib/ui/classes";
import type { PatientResponse } from "@/lib/api/types";

/**
 * Patients directory.
 *
 * The collection itself is the deck: one card per patient, the selected one in
 * front, the rest stepped behind it and reachable by swipe, tap or arrow key.
 * There is no second roster underneath — that would list the same patients
 * twice.
 *
 * Everything shown comes from `listPatients()` — name, age, sex and relation.
 * Initials only; no photo, no derived metric, no fabricated detail.
 */

/**
 * The user's own record leads; everyone else keeps the order the API returned.
 *
 * "Own record" is the `Self` relation, never recency — the newest record is
 * usually a dependant. If several records claim `Self`, the first stable
 * occurrence leads and the rest stay where the API put them. With no `Self` at
 * all the API order stands; there is nothing to infer from.
 *
 * Not exported: a route module may only export `default` and Next's own route
 * config, and the build type-checks that.
 */
function orderPatients(patients: PatientResponse[]): PatientResponse[] {
  const self = patients.findIndex((patient) => patient.relation === "Self");
  if (self < 0) return patients;
  return [patients[self], ...patients.slice(0, self), ...patients.slice(self + 1)];
}

export default function DashboardPage() {
  usePageTitle("Patients");
  const router = useRouter();
  const [patients, setPatients] = useState<PatientResponse[]>([]);
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState(0);

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

  const ordered = useMemo(() => orderPatients(patients), [patients]);
  // A reload can shorten the list under a selection made against the old one.
  const activeIndex = Math.min(selected, Math.max(ordered.length - 1, 0));
  // Counts the records the API returned; nothing here is derived about a patient.
  const subtitle =
    ordered.length > 0
      ? `${ordered.length} ${ordered.length === 1 ? "record" : "records"} · choose one to review`
      : "Choose a record to review";

  return (
    <AuthGate>
      <div className="pv-directory min-h-screen">
        <header>
          <div className="pv-directory-head">
            <div className="min-w-0">
              {email ? <p className="pv-directory-eyebrow truncate">{email}</p> : null}
              <h1 className="pv-directory-title">Patients</h1>
            </div>
            <div className="pv-directory-actions">
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
          </div>
          <p className="pv-directory-sub">{subtitle}</p>
        </header>

        {showForm ? (
          <div className="mt-7 rounded-card bg-surface p-5 shadow-[var(--e-panel)] sm:p-6">
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

        {!loading && !error && ordered.length === 0 ? (
          <section className="mt-9 rounded-card bg-surface px-6 py-14 text-center shadow-[var(--e-row)]">
            <h2 className="pv-section-title">No patients yet</h2>
            <p className="mx-auto mt-2 max-w-sm text-base leading-6 text-ink-2">
              Add a patient to start a medication record and run safety analysis.
            </p>
          </section>
        ) : null}

        {ordered.length > 0 ? (
          <div className="mt-7">
            <PatientDeck
              patients={ordered}
              activeIndex={activeIndex}
              onSelect={setSelected}
              onOpen={(patient) => router.push(`/patients/${patient.id}`)}
            />
            {ordered.length === 1 ? (
              <p className="pv-directory-note">
                This is your only record so far. Add another with the button above.
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </AuthGate>
  );
}
