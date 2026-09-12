"use client";

import Link from "next/link";
import { ArrowLeftIcon } from "@/components/icons/Icons";
import { patientInitials } from "@/components/PatientAvatar";
import { demographicLine } from "@/lib/patient/summaries";
import type { PatientResponse } from "@/lib/api/types";

/**
 * The identity surface, reproducing the reference hero's composition: a
 * full-bleed image plane with a floating circular control at the top-left and
 * the name and metadata set against its darkened foot.
 *
 * The reference uses photography, which a patient record cannot. The stand-in
 * keeps the same tonal composition — warm light in the upper right falling to
 * a deep mass at the lower left — so the layering and the white-on-dark type
 * read the same. It is identical for every patient and every render: identity
 * surfaces stay calm, and clinical state is never expressed here.
 */
export function PatientHero({
  patient,
  backHref,
  backLabel,
}: {
  patient: PatientResponse;
  backHref: string;
  backLabel: string;
}) {
  return (
    <header className="pv-hero on-dark">
      <div className="flex items-start justify-between">
        <Link href={backHref} aria-label={backLabel} className="rounded-full">
          <span className="pv-round" aria-hidden="true">
            <ArrowLeftIcon className="h-5 w-5" />
          </span>
        </Link>
        <span
          aria-label={`${patient.name} initials`}
          className="pv-initials h-11 w-11 text-sm sm:h-12 sm:w-12 sm:text-base"
        >
          {patientInitials(patient.name)}
        </span>
      </div>

      <div className="mt-auto pt-8">
        <h1 className="pv-hero-name">{patient.name}</h1>
        <p className="pv-hero-meta">{demographicLine(patient)}</p>
      </div>
    </header>
  );
}
