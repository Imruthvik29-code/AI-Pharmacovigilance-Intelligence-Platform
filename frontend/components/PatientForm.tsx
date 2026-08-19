"use client";

import { useState } from "react";
import { StatusBanner } from "@/components/StatusBanner";
import { createPatient } from "@/lib/api/patients";
import { ApiError } from "@/lib/api/errors";
import type { PatientResponse } from "@/lib/api/types";
import { fieldClass, primaryButtonClass } from "@/lib/ui/classes";

export function PatientForm({ onCreated }: { onCreated: (patient: PatientResponse) => void }) {
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const parsedAge = age.trim() === "" ? undefined : Number(age);
      const patient = await createPatient({
        name: name.trim(),
        age: parsedAge,
        sex: sex.trim() || undefined,
      });
      onCreated(patient);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not create patient.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="block text-sm font-medium" htmlFor="patient-name">
          Name
        </label>
        <input
          id="patient-name"
          required
          minLength={1}
          maxLength={200}
          value={name}
          onChange={(event) => setName(event.target.value)}
          className={fieldClass}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="block text-sm font-medium" htmlFor="patient-age">
            Age <span className="font-normal text-muted">(optional)</span>
          </label>
          <input
            id="patient-age"
            type="number"
            min={0}
            max={130}
            value={age}
            onChange={(event) => setAge(event.target.value)}
            className={fieldClass}
          />
        </div>
        <div>
          <label className="block text-sm font-medium" htmlFor="patient-sex">
            Sex <span className="font-normal text-muted">(optional)</span>
          </label>
          <input
            id="patient-sex"
            value={sex}
            onChange={(event) => setSex(event.target.value)}
            className={fieldClass}
          />
        </div>
      </div>
      {error ? (
        <StatusBanner tone="error" role="alert">
          {error}
        </StatusBanner>
      ) : null}
      <button
        type="submit"
        disabled={submitting || name.trim().length === 0}
        className={primaryButtonClass}
      >
        {submitting ? "Creating…" : "Create patient"}
      </button>
    </form>
  );
}
