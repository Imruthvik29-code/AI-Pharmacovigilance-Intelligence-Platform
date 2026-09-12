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
    size === "lg" ? "h-14 w-14 text-lg" : size === "sm" ? "h-9 w-9 text-[0.75rem]" : "h-12 w-12 text-[0.9375rem]";

  return (
    <span
      aria-label={`${patient.name} initials`}
      className={`${dimensions} inline-flex shrink-0 items-center justify-center rounded-full bg-surface-2 font-bold tracking-[-0.01em] text-ink`}
    >
      {patientInitials(patient.name)}
    </span>
  );
}
