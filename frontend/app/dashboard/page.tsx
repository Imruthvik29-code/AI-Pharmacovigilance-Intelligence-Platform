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
import { PatientAvatar } from "@/components/PatientAvatar";
import type { PatientResponse } from "@/lib/api/types";

export default function DashboardPage() {
  usePageTitle("Dashboard");
  const router = useRouter();
  const [patients, setPatients] = useState<PatientResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);

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

  const selectedPatient = patients.find((patient) => patient.id === selectedPatientId) ?? patients[0];

  return (
    <AuthGate>
      <AppShell>
        <section className="patient-list">
          <header className="patient-list-header">
            <div><p>Your clinical records</p><h1>Patients</h1></div>
            <button type="button" aria-label={showForm ? "Close patient form" : "Add patient"} onClick={() => setShowForm((open) => !open)} className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-ink text-2xl text-white shadow-[0_10px_24px_rgba(20,32,41,0.16)] transition-transform hover:-translate-y-0.5">{showForm ? "×" : "+"}</button>
          </header>
          {showForm ? <div className="mt-6 max-w-xl rounded-[2rem] border border-line bg-card p-5 shadow-[0_14px_35px_rgba(20,32,41,0.06)] sm:p-7"><h2 className="text-xl font-semibold">New patient</h2><p className="mt-1 text-sm text-muted">Create a record to start tracking treatment and safety.</p><div className="mt-5"><PatientForm onCreated={(patient) => router.push(`/patients/${patient.id}`)} /></div></div> : null}
          <div className="patient-list-content"><div className="patient-list-heading"><h2>Recent patients</h2><span>{patients.length} records</span></div>
          {loading ? <div className="max-w-md"><LoadingSkeleton label="Loading patients" lines={4} /></div> : null}
          {error ? <StatusBanner tone="error" role="alert">{error}</StatusBanner> : null}
          {!loading && !error && patients.length === 0 ? <section className="rounded-[2rem] border border-dashed border-line bg-card px-6 py-12 text-center"><h2 className="text-lg font-semibold">No patients yet</h2><p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted">Add a patient to start a medication record and run safety analysis.</p></section> : null}
          {!loading && patients.length > 0 ? <>
            <ul className="patient-picker" aria-label="Select a patient">{patients.map((patient) => <li key={patient.id}><button type="button" className={patient.id === selectedPatient?.id ? "is-selected" : ""} onClick={() => setSelectedPatientId(patient.id)} aria-pressed={patient.id === selectedPatient?.id}><PatientAvatar patient={patient} size="sm" /><span><strong>{patient.name}</strong><small>{patient.age != null ? `${patient.age} yrs` : "Age not recorded"}</small></span></button></li>)}</ul>
            {selectedPatient ? <button type="button" onClick={() => router.push(`/patients/${selectedPatient.id}`)} className="patient-preview" aria-label={`Open ${selectedPatient.name}`}><div className="patient-preview-mark" aria-hidden="true" /><PatientAvatar patient={selectedPatient} /><div className="patient-preview-copy"><p>{selectedPatient.name}</p><span>{[selectedPatient.age != null ? `${selectedPatient.age} yrs` : null, selectedPatient.sex].filter(Boolean).join(" · ") || "No demographics recorded"}</span>{selectedPatient.relation ? <small>{selectedPatient.relation === "Self" ? "My profile" : selectedPatient.relation}</small> : null}</div><div className="patient-preview-action"><span>View patient</span><b aria-hidden="true">→</b></div></button> : null}
          </> : null}</div>
        </section>
      </AppShell>
    </AuthGate>
  );
}
