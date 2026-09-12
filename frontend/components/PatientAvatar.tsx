import type { PatientResponse } from "@/lib/api/types";

export function patientInitials(name: string): string {
  return (
    name
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "?"
  );
}

/** Identity is initials only. No photo is ever stored or rendered. */
export function PatientAvatar({
  patient,
  size = "md",
}: {
  patient: Pick<PatientResponse, "name">;
  size?: "sm" | "md" | "lg";
}) {
  const dimensions =
    size === "lg" ? "h-16 w-16 text-xl" : size === "sm" ? "h-9 w-9 text-[0.75rem]" : "h-[3.25rem] w-[3.25rem] text-[1rem]";

  return (
    <span
      aria-label={`${patient.name} initials`}
      className={`${dimensions} pv-identity-chip`}
    >
      {patientInitials(patient.name)}
    </span>
  );
}
