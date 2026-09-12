/**
 * Inline SVG icon set. Replaces the previous typographic glyphs (⌁ ＋ ◌ ◷),
 * which rendered inconsistently across platforms and were absent from several
 * Android font stacks. All icons share a 24px box and a 1.6 stroke so they sit
 * optically level inside an IconChip.
 */
type IconProps = { className?: string };

function base(className?: string) {
  return {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
    className: className ?? "h-[1.35em] w-[1.35em]",
  };
}

export function ShieldIcon({ className }: IconProps) {
  return (
    <svg {...base(className)}>
      <path d="M12 3.2 19 6v5.4c0 4.2-2.8 7.4-7 9.4-4.2-2-7-5.2-7-9.4V6l7-2.8Z" />
      <path d="M12 8.6v4" />
      <path d="M12 15.6h.01" />
    </svg>
  );
}

export function CapsuleIcon({ className }: IconProps) {
  return (
    <svg {...base(className)}>
      <rect x="2.8" y="8.6" width="18.4" height="6.8" rx="3.4" transform="rotate(-38 12 12)" />
      <path d="M9.1 8.2 14.9 15" />
    </svg>
  );
}

export function PulseIcon({ className }: IconProps) {
  return (
    <svg {...base(className)}>
      <path d="M3 12.4h3.6L9 7.2l3.4 9.6 2.3-4.4H21" />
    </svg>
  );
}

export function CalendarIcon({ className }: IconProps) {
  return (
    <svg {...base(className)}>
      <rect x="3.6" y="5.2" width="16.8" height="15.2" rx="3.2" />
      <path d="M3.6 10h16.8M8.4 3.6v3.2M15.6 3.6v3.2" />
    </svg>
  );
}

export function ArrowRightIcon({ className }: IconProps) {
  return (
    <svg {...base(className)}>
      <path d="M5 12h13.5M13 6.5 18.8 12 13 17.5" />
    </svg>
  );
}

export function ArrowLeftIcon({ className }: IconProps) {
  return (
    <svg {...base(className)}>
      <path d="M19 12H5.5M11 6.5 5.2 12 11 17.5" />
    </svg>
  );
}

export function AlertIcon({ className }: IconProps) {
  return (
    <svg {...base(className)}>
      <path d="M12 4.4 21 19.6H3L12 4.4Z" />
      <path d="M12 10.2v3.4" />
      <path d="M12 16.6h.01" />
    </svg>
  );
}

export function ClockIcon({ className }: IconProps) {
  return (
    <svg {...base(className)}>
      <circle cx="12" cy="12" r="8.4" />
      <path d="M12 7.4V12l3 1.8" />
    </svg>
  );
}

export function DocumentIcon({ className }: IconProps) {
  return (
    <svg {...base(className)}>
      <path d="M6.4 3.6h7.2L18.4 8.4v12H6.4V3.6Z" />
      <path d="M13.4 3.8v4.8h4.8M9.2 13h5.6M9.2 16.4h5.6" />
    </svg>
  );
}

export function SparkIcon({ className }: IconProps) {
  return (
    <svg {...base(className)}>
      <path d="M12 3.6 13.7 9l5.4 1.7-5.4 1.7L12 17.8l-1.7-5.4L4.9 10.7 10.3 9 12 3.6Z" />
    </svg>
  );
}

export function CheckIcon({ className }: IconProps) {
  return (
    <svg {...base(className)}>
      <circle cx="12" cy="12" r="8.4" />
      <path d="M8.4 12.2 11 14.8l4.6-5" />
    </svg>
  );
}

export function PlusIcon({ className }: IconProps) {
  return (
    <svg {...base(className)}>
      <path d="M12 5.4v13.2M5.4 12h13.2" />
    </svg>
  );
}
