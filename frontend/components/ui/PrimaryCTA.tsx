"use client";

import { ArrowRightIcon } from "@/components/icons/Icons";

/**
 * The reference's primary action: a dark pill with the label set left and a
 * white circular trailing affordance. 64px tall, fully rounded, 48px badge.
 */
export function PrimaryCTA({
  children,
  onClick,
  disabled,
  busy,
  type = "button",
  ariaLabel,
  tabIndex,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  busy?: boolean;
  type?: "button" | "submit";
  ariaLabel?: string;
  tabIndex?: number;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      aria-busy={busy || undefined}
      aria-label={ariaLabel}
      tabIndex={tabIndex}
      className="pv-cta on-dark"
    >
      <span className="truncate">{children}</span>
      <span className="pv-cta-badge" aria-hidden="true">
        <ArrowRightIcon className="h-5 w-5" />
      </span>
    </button>
  );
}
