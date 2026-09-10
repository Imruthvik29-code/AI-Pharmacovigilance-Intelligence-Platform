import type { PatientResponse } from "@/lib/api/types";

export function patientInitials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "?";
}

export function PatientAvatar({
  patient,
  size = "md",
}: {
  patient: Pick<PatientResponse, "name">;
  size?: "sm" | "md" | "lg";
}) {
  const dimensions = size === "lg" ? "h-24 w-24 text-3xl" : size === "sm" ? "h-11 w-11 text-sm" : "h-16 w-16 text-xl";

  return (
    <span
      aria-label={`${patient.name} initials`}
      className={`${dimensions} inline-flex shrink-0 items-center justify-center rounded-[1.35rem] border border-[#b8d7d2] bg-[#e7f2ef] font-semibold tracking-tight text-accent shadow-[0_8px_20px_rgba(20,32,41,0.05)]`}
    >
      {patientInitials(patient.name)}
    </span>
  );
}
