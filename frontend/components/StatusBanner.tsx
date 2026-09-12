type Tone = "error" | "info" | "success";

const tones: Record<Tone, { surface: string; ink: string }> = {
  error: { surface: "var(--severe-surface)", ink: "var(--severe-ink)" },
  info: { surface: "var(--surface-sunk)", ink: "var(--ink)" },
  success: { surface: "var(--mild-surface)", ink: "var(--mild-ink)" },
};

export function StatusBanner({
  tone,
  children,
  role = "status",
}: {
  tone: Tone;
  children: React.ReactNode;
  role?: "status" | "alert";
}) {
  const style = tones[tone];
  return (
    <div
      role={role}
      className="rounded-md px-4 py-3 text-[0.875rem] leading-6"
      style={{ backgroundColor: style.surface, color: style.ink }}
    >
      {children}
    </div>
  );
}
