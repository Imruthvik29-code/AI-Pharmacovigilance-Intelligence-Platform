import type { ReactNode } from "react";

type Tone = "neutral" | "positive" | "warning" | "critical";

export function PatientSectionDetail({
  eyebrow,
  title,
  description,
  onBack,
  children,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  onBack: () => void;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <article className="mx-auto w-full max-w-3xl pb-24">
      <PatientDetailBack onClick={onBack} />
      <header className="border-b border-line pb-6 pt-5 sm:pb-8 sm:pt-8">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">{eyebrow}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] sm:text-5xl">{title}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted sm:text-base">{description}</p>
      </header>
      <div className="space-y-6 py-6 sm:py-8">{children}</div>
      {action ? <PatientDetailAction>{action}</PatientDetailAction> : null}
    </article>
  );
}

export function PatientDetailBack({ onClick, label = "Patient overview" }: { onClick: () => void; label?: string }) {
  return (
    <button type="button" onClick={onClick} className="patient-back-link" aria-label={`Back to ${label.toLowerCase()}`}>
      <span aria-hidden="true">←</span> {label}
    </button>
  );
}

export function PatientInformationRows({ children, label = "Section summary" }: { children: ReactNode; label?: string }) {
  return <dl className="grid overflow-hidden rounded-2xl border border-line bg-card sm:grid-cols-2" aria-label={label}>{children}</dl>;
}

export function PatientInformationRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="border-b border-line px-4 py-3 last:border-b-0 sm:border-r sm:[&:nth-last-child(-n+2)]:border-b-0 sm:[&:nth-child(2n)]:border-r-0">
      <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</dt>
      <dd className="mt-1 text-sm font-medium text-ink">{value}</dd>
    </div>
  );
}

export function PatientFindingRow({ label, detail, value, tone = "neutral" }: { label: string; detail?: string; value: ReactNode; tone?: Tone }) {
  const tones: Record<Tone, string> = {
    neutral: "border-line bg-card text-muted",
    positive: "border-accent/30 bg-accent/5 text-accent",
    warning: "border-medium/30 bg-medium/5 text-medium",
    critical: "border-high/30 bg-high/5 text-high",
  };
  return (
    <div className={`flex items-start justify-between gap-4 rounded-xl border px-4 py-3 ${tones[tone]}`}>
      <div><p className="text-sm font-medium text-ink">{label}</p>{detail ? <p className="mt-1 text-xs leading-5 text-muted">{detail}</p> : null}</div>
      <span className="shrink-0 rounded-full border border-current/20 px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-wide">{value}</span>
    </div>
  );
}

export function PatientDetailAction({ children }: { children: ReactNode }) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-paper/95 px-4 py-3 shadow-[0_-8px_24px_rgba(20,32,41,0.06)] backdrop-blur sm:sticky sm:-mx-4 sm:px-4">
      <div className="mx-auto flex w-full max-w-3xl justify-end">{children}</div>
    </div>
  );
}
