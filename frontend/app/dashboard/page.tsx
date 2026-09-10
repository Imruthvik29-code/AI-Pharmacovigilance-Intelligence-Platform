"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { PatientAvatar } from "@/components/PatientAvatar";
import { PatientForm } from "@/components/PatientForm";
import { StatusBanner } from "@/components/StatusBanner";
import { ApiError } from "@/lib/api/errors";
import { listPatients } from "@/lib/api/patients";
import type { PatientResponse } from "@/lib/api/types";
import { usePageTitle } from "@/lib/hooks/usePageTitle";

function demographics(patient: PatientResponse) {
  return [patient.age != null ? `${patient.age} yrs` : null, patient.sex].filter(Boolean).join(" · ") || "No demographics recorded";
}

export default function DashboardPage() {
  usePageTitle("Patients");
  const router = useRouter();
  const [patients, setPatients] = useState<PatientResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
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
        if (!cancelled) {
          setPatients(rows);
          setSelectedId(rows[0]?.id ?? null);
        }
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
    return () => { cancelled = true; };
  }, [router]);

  const filteredPatients = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    if (!term) return patients;
    return patients.filter((patient) => [patient.name, patient.relation, patient.sex].some((value) => value?.toLocaleLowerCase().includes(term)));
  }, [patients, query]);
  const selectedPatient = filteredPatients.find((patient) => patient.id === selectedId) ?? filteredPatients[0] ?? null;

  return (
    <AuthGate>
      <AppShell>
        <section className="dashboard-patients">
          <header className="dashboard-heading">
            <div>
              <p className="patient-hero-kicker">Your clinical records</p>
              <h1>Good to see you.</h1>
              <p>Choose a patient to continue their care record.</p>
            </div>
            <button type="button" aria-label={showForm ? "Close patient form" : "Add patient"} onClick={() => setShowForm((open) => !open)} className="dashboard-add-button">{showForm ? "×" : "+"}</button>
          </header>

          {showForm ? <div className="mt-6 max-w-xl rounded-[2rem] border border-line bg-card p-5 shadow-[0_14px_35px_rgba(20,32,41,0.06)] sm:p-7"><h2 className="text-xl font-semibold">New patient</h2><p className="mt-1 text-sm text-muted">Create a record to start tracking treatment and safety.</p><div className="mt-5"><PatientForm onCreated={(patient) => router.push(`/patients/${patient.id}`)} /></div></div> : null}

          {loading ? <div className="mt-8 max-w-md"><LoadingSkeleton label="Loading patients" lines={4} /></div> : null}
          {error ? <div className="mt-8"><StatusBanner tone="error" role="alert">{error}</StatusBanner></div> : null}
          {!loading && !error && patients.length === 0 ? <section className="mt-8 rounded-[2rem] border border-dashed border-line bg-card px-6 py-12 text-center"><h2 className="text-lg font-semibold">No patients yet</h2><p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted">Add a patient to start a medication record and run safety analysis.</p></section> : null}

          {!loading && !error && patients.length > 0 ? (
            <div className="mt-7">
              <div className="dashboard-list-heading">
                <div><h2>Patients</h2><span>{patients.length} {patients.length === 1 ? "record" : "records"}</span></div>
                <label className="dashboard-search"><span className="sr-only">Search patients</span><span aria-hidden="true">⌕</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search patients" /></label>
              </div>

              {filteredPatients.length > 0 ? (
                <>
                  <ul className="dashboard-patient-rail" aria-label="Patient records">
                    {filteredPatients.map((patient, index) => {
                      const active = patient.id === selectedPatient?.id;
                      return <li key={patient.id}><button type="button" title={`Preview ${patient.name}`} aria-label={active ? "Selected patient" : `Select patient record ${index + 1}`} aria-pressed={active} onClick={() => setSelectedId(patient.id)} className={`dashboard-patient-chip ${active ? "is-active" : ""}`}><PatientAvatar patient={patient} size="sm" /><span><strong aria-hidden="true">{patient.name.split(/\s+/).map((part, partIndex) => <span key={`${part}-${partIndex}`}>{part}{partIndex < patient.name.split(/\s+/).length - 1 ? " " : ""}</span>)}</strong><small>{patient.relation === "Self" ? "My profile" : patient.relation || demographics(patient)}</small></span></button></li>;
                    })}
                  </ul>

                  {selectedPatient ? <section className="dashboard-preview-deck" aria-label="Selected patient preview">
                    <div className="dashboard-preview-stage">
                      <div className="workspace-card-shadow workspace-card-shadow-one" aria-hidden="true" />
                      <div className="workspace-card-shadow workspace-card-shadow-two" aria-hidden="true" />
                      <button type="button" onClick={() => router.push(`/patients/${selectedPatient.id}`)} className="dashboard-preview-card" aria-label={`Open ${selectedPatient.name}'s patient record`}>
                        <div className="dashboard-preview-top"><PatientAvatar patient={selectedPatient} size="lg" /><div><p className="workspace-eyebrow">Selected patient</p><h2>{selectedPatient.name}</h2><p>{demographics(selectedPatient)}</p></div></div>
                        <div className="dashboard-preview-copy">
                          <p className="dashboard-preview-relation">{selectedPatient.relation === "Self" ? "My profile" : selectedPatient.relation || "Patient record"}</p>
                          <div className="dashboard-metadata">
                            <span><small>Weight</small><strong>{selectedPatient.weight_kg != null ? `${selectedPatient.weight_kg} kg` : "Not recorded"}</strong></span>
                            <span><small>Clinical flags</small><strong>{selectedPatient.renal_flag || selectedPatient.hepatic_flag ? [selectedPatient.renal_flag ? "Renal" : null, selectedPatient.hepatic_flag ? "Hepatic" : null].filter(Boolean).join(" · ") : "None recorded"}</strong></span>
                          </div>
                        </div>
                        <span className="workspace-primary-action">Open patient record <span aria-hidden="true">→</span></span>
                      </button>
                    </div>
                  </section> : null}
                </>
              ) : <div className="mt-5 rounded-3xl border border-dashed border-line px-5 py-9 text-center"><h3 className="font-semibold">No matching patients</h3><p className="mt-1 text-sm text-muted">Try a different name, relation, or demographic.</p></div>}
            </div>
          ) : null}
        </section>
      </AppShell>
    </AuthGate>
  );
}
