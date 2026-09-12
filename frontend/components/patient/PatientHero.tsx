"use client";

import Link from "next/link";
import { ArrowLeftIcon } from "@/components/icons/Icons";
import { patientInitials } from "@/components/PatientAvatar";
import { demographicLine } from "@/lib/patient/summaries";
import type { PatientResponse } from "@/lib/api/types";

type BackAction = { label: string; href?: string; onClick?: () => void };

/**
 * Dark identity surface the foreground card overlaps.
 *
 * The surface is intentionally identical for every patient and every render —
 * no per-patient gradient, no risk colouring. Patient identity stays visually
 * stable; clinical state is expressed by severity pills and findings surfaces.
 */
export function PatientHero({
  patient,
  variant = "full",
  back,
}: {
  patient: PatientResponse;
  variant?: "full" | "compact";
  back: BackAction;
}) {
  const compact = variant === "compact";
  const control = (
    <span className="px-round" aria-hidden="true">
      <ArrowLeftIcon className="h-5 w-5" />
    </span>
  );

  return (
    <header className={`px-hero on-dark ${compact ? "px-hero-compact" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        {back.href ? (
          <Link href={back.href} aria-label={back.label} className="rounded-full">
            {control}
          </Link>
        ) : (
          <button type="button" onClick={back.onClick} aria-label={back.label} className="rounded-full">
            {control}
          </button>
        )}
      </div>

      <div className={`flex items-end gap-4 ${compact ? "mt-4" : "mt-auto pt-6"}`}>
        <span
          aria-label={`${patient.name} initials`}
          className={`px-initials ${compact ? "h-12 w-12 text-base" : "h-14 w-14 text-lg sm:h-16 sm:w-16 sm:text-xl"}`}
        >
          {patientInitials(patient.name)}
        </span>
        <div className="min-w-0">
          {compact ? null : <p className="px-hero-eyebrow">Patient record</p>}
          <h1 className={`px-hero-name ${compact ? "!text-[1.5rem] sm:!text-[1.75rem]" : ""}`}>
            {patient.name}
          </h1>
          <p className="px-hero-meta">{demographicLine(patient)}</p>
        </div>
      </div>
    </header>
  );
}
