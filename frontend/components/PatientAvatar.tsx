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
    size === "lg" ? "h-16 w-16 text-xl" : size === "sm" ? "h-11 w-11 text-sm" : "h-14 w-14 text-base";

  return (
    <span
      aria-label={`${patient.name} initials`}
      className={`${dimensions} inline-flex shrink-0 items-center justify-center rounded-md bg-identity font-semibold tracking-[-0.01em] text-white`}
    >
      {patientInitials(patient.name)}
    </span>
  );
}
