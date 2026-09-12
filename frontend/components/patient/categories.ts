import type { ComponentType } from "react";
import { CalendarIcon, CapsuleIcon, PulseIcon, ShieldIcon } from "@/components/icons/Icons";

/**
 * Single registry for the four clinical categories. Labels, ordering, colour
 * tokens and icons live here only — previously these were duplicated across the
 * workspace component, the page eyebrows and positional `nth-child` CSS rules,
 * which let them drift apart.
 */
export type CategoryId = "safety" | "medications" | "symptoms" | "timeline";

export type Category = {
  id: CategoryId;
  label: string;
  number: string;
  description: string;
  Icon: ComponentType<{ className?: string }>;
  /** Tint used for the ribbon tab and icon chip. */
  surface: string;
  ink: string;
};

export const CATEGORIES: readonly Category[] = [
  {
    id: "safety",
    label: "Safety",
    number: "01",
    description: "Interaction, ADR and adherence findings for this record.",
    Icon: ShieldIcon,
    surface: "var(--safety-surface)",
    ink: "var(--safety-ink)",
  },
  {
    id: "medications",
    label: "Medications",
    number: "02",
    description: "Prescribed courses, dosing schedule and adherence.",
    Icon: CapsuleIcon,
    surface: "var(--medications-surface)",
    ink: "var(--medications-ink)",
  },
  {
    id: "symptoms",
    label: "Symptoms",
    number: "03",
    description: "Reported symptoms, severity and linked medication.",
    Icon: PulseIcon,
    surface: "var(--symptoms-surface)",
    ink: "var(--symptoms-ink)",
  },
  {
    id: "timeline",
    label: "Timeline",
    number: "04",
    description: "Every recorded event, most recent first.",
    Icon: CalendarIcon,
    surface: "var(--timeline-surface)",
    ink: "var(--timeline-ink)",
  },
] as const;

export function isCategoryId(value: string | null | undefined): value is CategoryId {
  return CATEGORIES.some((category) => category.id === value);
}

export function getCategory(id: CategoryId): Category {
  const found = CATEGORIES.find((category) => category.id === id);
  if (!found) throw new Error(`Unknown category: ${id}`);
  return found;
}

export function categoryIndex(id: CategoryId): number {
  return CATEGORIES.findIndex((category) => category.id === id);
}
