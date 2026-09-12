"use client";

import { useEffect, useRef } from "react";
import { ArrowLeftIcon } from "@/components/icons/Icons";
import { IconChip } from "@/components/ui/IconChip";
import { patientInitials } from "@/components/PatientAvatar";
import { getCategory, type CategoryId } from "@/components/patient/categories";
import type { PatientResponse } from "@/lib/api/types";

/**
 * The category detail screen, reconstructed from the reference's third frame:
 * plain canvas, a floating circular back control, a large tinted icon chip
 * with the title and description beneath it, then stacked rows, with the
 * primary action at the foot.
 *
 * Focus moves to the heading when the category changes so keyboard and screen
 * reader users land on the new screen rather than on a control that is gone.
 */
export function DetailScreen({
  categoryId,
  patient,
  title,
  description,
  onBack,
  footer,
  children,
}: {
  categoryId: CategoryId;
  patient: PatientResponse;
  title: string;
  description: string;
  onBack: () => void;
  footer?: React.ReactNode;
  children: React.ReactNode;
}) {
  const category = getCategory(categoryId);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, [categoryId]);

  return (
    <div>
      <div className="pv-topbar">
        <button type="button" onClick={onBack} aria-label="Back to overview" className="rounded-full">
          <span className="pv-round pv-round-light" aria-hidden="true">
            <ArrowLeftIcon className="h-5 w-5" />
          </span>
        </button>

        {/* Clinical context the reference has no need for: whose record this is. */}
        <span className="flex min-w-0 items-center gap-2 rounded-full bg-surface px-3 py-1.5 shadow-[var(--e-row)]">
          <span
            aria-hidden="true"
            className="inline-flex h-6 w-6 flex-none items-center justify-center rounded-full bg-surface-2 text-[0.6875rem] font-bold text-ink-2"
          >
            {patientInitials(patient.name)}
          </span>
          <span className="truncate text-[0.8125rem] font-semibold text-ink-2">{patient.name}</span>
        </span>
      </div>

      <section className="pv-detail pt-7 lg:pt-10" aria-labelledby="detail-heading">
        <div className="flex items-start gap-3.5">
          <IconChip
            Icon={category.Icon}
            surface={category.surface}
            ink={category.ink}
            size="lg"
            className="mt-0.5"
          />
          <div className="min-w-0">
            <h1
              id="detail-heading"
              ref={headingRef}
              tabIndex={-1}
              className="pv-detail-title pv-quiet-focus"
            >
              {title}
            </h1>
            <p className="pv-detail-desc">{description}</p>
          </div>
        </div>

        <div className="mt-5 space-y-6">{children}</div>

        {footer ? <div className="mt-8">{footer}</div> : null}
      </section>
    </div>
  );
}
