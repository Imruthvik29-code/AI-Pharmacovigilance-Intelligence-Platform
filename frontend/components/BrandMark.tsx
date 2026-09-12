export function BrandMark({ size = "md" }: { size?: "sm" | "md" }) {
  const mark = size === "sm" ? "h-9 w-9 text-[0.6875rem]" : "h-11 w-11 text-[0.8125rem]";
  return (
    <span
      aria-hidden
      className={`inline-flex ${mark} items-center justify-center rounded-row bg-identity font-semibold tracking-wide text-white`}
    >
      PV
    </span>
  );
}
