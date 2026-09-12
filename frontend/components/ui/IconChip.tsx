import type { ComponentType } from "react";

const SIZES = {
  sm: "h-9 w-9 text-[0.8rem]",
  md: "h-11 w-11 text-[0.95rem]",
  lg: "h-14 w-14 text-[1.15rem]",
} as const;

/**
 * Tinted circle holding one line icon. `surface`/`ink` are CSS colour values
 * (usually category or severity tokens) so the chip carries category identity
 * without needing a class per category.
 */
export function IconChip({
  Icon,
  surface,
  ink,
  size = "md",
  className,
}: {
  Icon: ComponentType<{ className?: string }>;
  surface: string;
  ink: string;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={`inline-flex flex-none items-center justify-center rounded-full ${SIZES[size]} ${className ?? ""}`}
      style={{ backgroundColor: surface, color: ink }}
    >
      <Icon className={size === "lg" ? "h-7 w-7" : size === "sm" ? "h-[1.05rem] w-[1.05rem]" : "h-5 w-5"} />
    </span>
  );
}
