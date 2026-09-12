"use client";

import { ArrowRightIcon } from "@/components/icons/Icons";

/**
 * Dark pill CTA with a white circular trailing affordance.
 * `block` fills its container (mobile); `inline` stays a contained pill so the
 * shape survives on wide viewports.
 */
export function PillButton({
  children,
  onClick,
  disabled,
  busy,
  width = "block",
  type = "button",
  ariaLabel,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  busy?: boolean;
  width?: "block" | "inline";
  type?: "button" | "submit";
  ariaLabel?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      aria-busy={busy || undefined}
      aria-label={ariaLabel}
      className={`px-pill on-dark ${width === "block" ? "px-pill-block" : "max-w-80"}`}
    >
      <span className="truncate">{children}</span>
      <span className="px-pill-badge" aria-hidden="true">
        <ArrowRightIcon className="h-5 w-5" />
      </span>
    </button>
  );
}
