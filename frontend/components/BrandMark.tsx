export function BrandMark({ size = "md" }: { size?: "sm" | "md" }) {
  const mark = size === "sm" ? "h-8 w-8 text-[10px]" : "h-10 w-10 text-xs";
  return (
    <span
      aria-hidden
      className={`inline-flex ${mark} items-center justify-center rounded-lg bg-accent font-semibold tracking-wide text-white`}
    >
      PV
    </span>
  );
}
