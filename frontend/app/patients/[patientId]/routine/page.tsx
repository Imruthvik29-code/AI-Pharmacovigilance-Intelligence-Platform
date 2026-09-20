"use client";

import { useParams } from "next/navigation";
import { AuthGate } from "@/components/AuthGate";
import { PatientRoutineForm } from "@/components/PatientRoutineForm";

/**
 * Standalone surface for recording an existing patient's daily routine.
 * Deliberately self-contained: no frozen screen links here yet, so the
 * Directory, Patient Overview and DetailScreen header stay untouched.
 */
export default function PatientRoutinePage() {
  const params = useParams<{ patientId: string }>();
  const patientId = params?.patientId ?? "";

  return (
    <AuthGate>
      <main className="mx-auto w-full max-w-xl px-4 py-8">
        <PatientRoutineForm patientId={patientId} />
      </main>
    </AuthGate>
  );
}
