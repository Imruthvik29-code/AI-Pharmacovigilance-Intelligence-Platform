"use client";

import { useState } from "react";
import { StatusBanner } from "@/components/StatusBanner";
import { createPatient } from "@/lib/api/patients";
import { ApiError } from "@/lib/api/errors";
import type { PatientResponse } from "@/lib/api/types";
import { fieldClass, primaryButtonClass } from "@/lib/ui/classes";

const relations = ["Self", "Parent", "Spouse", "Child", "Sibling", "Grandparent", "Other", "Caregiver / dependent"];
export function PatientForm({ onCreated }: { onCreated: (patient: PatientResponse) => void }) {
  const [name, setName] = useState(""); const [age, setAge] = useState(""); const [sex, setSex] = useState(""); const [relation, setRelation] = useState(""); const [photo, setPhoto] = useState<string | null>(null); const [submitting, setSubmitting] = useState(false); const [error, setError] = useState<string | null>(null);
  async function handlePhoto(file?: File) { if (!file) return; if (!file.type.startsWith("image/")) { setError("Please choose an image file."); return; } const reader = new FileReader(); reader.onload = () => setPhoto(typeof reader.result === "string" ? reader.result : null); reader.readAsDataURL(file); }
  async function handleSubmit(event: React.FormEvent) { event.preventDefault(); if (submitting) return; setSubmitting(true); setError(null); try { const patient = await createPatient({ name: name.trim(), age: age.trim() === "" ? undefined : Number(age), sex: sex.trim() || undefined, relation: relation || undefined, photo_url: photo }); onCreated(patient); } catch (err) { setError(err instanceof ApiError ? err.detail : "Could not create patient."); } finally { setSubmitting(false); } }
  return <form onSubmit={handleSubmit} className="space-y-4">
    <div className="rounded-2xl border border-dashed border-line bg-paper/40 p-4"><label className="block text-sm font-medium" htmlFor="patient-photo">Patient photo <span className="font-normal text-muted">(Optional)</span></label><p className="mt-1 text-xs text-muted">Add a photo to help identify this patient.</p><div className="mt-3 flex items-center gap-3">{photo ? <img src={photo} alt="Selected patient" className="h-12 w-12 rounded-2xl object-cover" /> : null}<input id="patient-photo" type="file" accept="image/*" className="block text-xs text-muted file:mr-3 file:rounded-full file:border-0 file:bg-[#e7f2ef] file:px-3 file:py-2 file:font-medium file:text-accent" onChange={(event) => void handlePhoto(event.target.files?.[0])} /></div></div>
    <div><label className="block text-sm font-medium" htmlFor="patient-name">Name</label><input id="patient-name" required minLength={1} maxLength={200} value={name} onChange={(e) => setName(e.target.value)} className={fieldClass} /></div>
    <div className="grid gap-3 sm:grid-cols-2"><div><label className="block text-sm font-medium" htmlFor="patient-age">Age <span className="font-normal text-muted">(optional)</span></label><input id="patient-age" type="number" min={0} max={130} value={age} onChange={(e) => setAge(e.target.value)} className={fieldClass} /></div><div><label className="block text-sm font-medium" htmlFor="patient-sex">Sex <span className="font-normal text-muted">(optional)</span></label><input id="patient-sex" value={sex} onChange={(e) => setSex(e.target.value)} className={fieldClass} /></div></div>
    <div><label className="block text-sm font-medium" htmlFor="patient-relation">Relation to you <span className="font-normal text-muted">(optional)</span></label><select id="patient-relation" value={relation} onChange={(e) => setRelation(e.target.value)} className={fieldClass}><option value="">Select relation</option>{relations.map((item) => <option key={item}>{item}</option>)}</select></div>
    {error ? <StatusBanner tone="error" role="alert">{error}</StatusBanner> : null}<button type="submit" disabled={submitting || name.trim().length === 0} className={primaryButtonClass}>{submitting ? "Creating…" : "Create patient"}</button>
  </form>;
}
