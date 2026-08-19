import { EDUCATIONAL_DISCLAIMER } from "@/lib/analysis/deterministic";

export function Disclaimer({ compact = false }: { compact?: boolean }) {
  return (
    <p className={compact ? "text-xs leading-5 text-muted" : "text-sm leading-6 text-muted"}>
      {EDUCATIONAL_DISCLAIMER}
    </p>
  );
}
