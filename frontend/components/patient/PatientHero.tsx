"use client";

import Link from "next/link";
import { ArrowLeftIcon } from "@/components/icons/Icons";
import { patientInitials } from "@/components/PatientAvatar";
import { demographicLine } from "@/lib/patient/summaries";
import type { PatientResponse } from "@/lib/api/types";

/**
 * The identity surface: the reference's scenic hero, with the patient's name
 * and demographics set against its darkened lower edge and a light circular
 * back control floating over the scenery.
 *
 * The scenery is shared decoration — the same layered ridges as the directory
 * cards, drawn larger — so the card a user taps visibly becomes this surface.
 * It is identical for every patient and every render: it is not a photograph
 * of anyone and never encodes clinical state.
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
      <HeroScenery />

      <Link href={backHref} aria-label={backLabel} className="pv-hero-back rounded-full">
        <span className="pv-round pv-round-light" aria-hidden="true">
          <ArrowLeftIcon className="h-5 w-5" />
        </span>
      </Link>

      <div className="pv-hero-identity">
        <span aria-label={`${patient.name} initials`} className="pv-hero-mark">
          {patientInitials(patient.name)}
        </span>
        <h1 className="pv-hero-name">{patient.name}</h1>
        <p className="pv-hero-meta">{demographicLine(patient)}</p>
      </div>
    </header>
  );
}

/**
 * Layered ridges receding into a warm horizon, with still water in front.
 * Stretched to the surface like the directory card's folds, so every shape
 * stays inside the hero rather than being cropped beyond its edges.
 */
function HeroScenery() {
  return (
    <svg
      className="pv-hero-scenery"
      viewBox="0 0 1440 900"
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        className="pv-ridge-far"
        d="M0 520C120 470 210 430 330 452C430 470 500 400 610 372C700 350 790 410 880 430C990 455 1080 390 1190 402C1290 412 1370 460 1440 452V900H0Z"
      />
      <path
        className="pv-ridge-mid"
        d="M0 604C140 562 262 522 402 550C522 574 622 532 742 508C862 484 982 550 1102 562C1222 574 1332 532 1440 542V900H0Z"
      />
      <path
        className="pv-ridge-near"
        d="M0 672C180 636 330 654 480 644C640 634 760 604 920 626C1080 648 1240 614 1440 632V900H0Z"
      />
      <path className="pv-water" d="M0 730C300 716 600 736 900 722C1140 712 1300 728 1440 720V900H0Z" />
      <path className="pv-water-light" d="M150 770C400 760 640 776 890 764M520 812C760 804 960 818 1180 808" />
    </svg>
  );
}
