/**
 * Shared control classes.
 *
 * The patient surfaces use the pill system in `globals.css` (`.px-pill`,
 * `.px-pill-quiet`). These exports cover forms and the auth pages, restyled
 * onto the same cool token set but keeping their existing shapes so the
 * login/signup flows are untouched by the patient redesign.
 */

export const fieldClass =
  "mt-1 w-full min-h-11 rounded-row bg-surface-2 px-3.5 py-2.5 text-ink placeholder:text-ink-3";

export const fieldOnCardClass =
  "mt-1 w-full min-h-11 rounded-row bg-surface-2 px-3.5 py-2.5 text-ink placeholder:text-ink-3";

/** For fields sitting on a sunk panel, where a sunk field would disappear. */
export const fieldOnSunkClass =
  "mt-1 w-full min-h-11 rounded-row bg-surface px-3.5 py-2.5 text-ink placeholder:text-ink-3";

export const primaryButtonClass =
  "on-dark inline-flex min-h-11 items-center justify-center rounded-full bg-cta px-5 py-2.5 text-sm font-semibold text-white transition hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-60";

export const secondaryButtonClass =
  "inline-flex min-h-11 items-center justify-center rounded-full bg-surface px-5 py-2.5 text-sm font-semibold text-ink shadow-[var(--e-row)] transition hover:shadow-[var(--e-float)] disabled:cursor-not-allowed disabled:opacity-60";

export const ghostButtonClass =
  "inline-flex min-h-11 items-center justify-center rounded-full px-3.5 py-2 text-sm font-medium text-ink-2 transition hover:bg-surface hover:text-ink";

export const cardClass = "rounded-card bg-surface shadow-[var(--e-float)]";
