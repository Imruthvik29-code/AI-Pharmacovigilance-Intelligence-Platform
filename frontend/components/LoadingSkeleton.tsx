export function LoadingSkeleton({
  lines = 3,
  label = "Loading",
}: {
  lines?: number;
  label?: string;
}) {
  return (
    <div role="status" aria-live="polite" aria-label={label} className="space-y-2.5">
      {Array.from({ length: lines }, (_, index) => (
        <div
          key={index}
          className="h-3 animate-pulse rounded-full bg-surface-sunk"
          style={{ width: `${88 - index * 12}%` }}
        />
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function CardSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="rounded-md bg-surface px-5 py-6 shadow-[var(--e1)]">
      <div className="h-3 w-24 animate-pulse rounded-full bg-surface-sunk" />
      <div className="mt-4 h-10 w-20 animate-pulse rounded-md bg-surface-sunk" />
      <div className="mt-3 h-3 w-2/3 animate-pulse rounded-full bg-surface-sunk" />
      <span className="sr-only">{label}</span>
    </div>
  );
}
