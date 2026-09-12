type Tone = "error" | "info" | "success";

const tones: Record<Tone, { surface: string; ink: string }> = {
  error: { surface: "var(--severe-bg)", ink: "var(--severe-fg)" },
  info: { surface: "var(--surface-2)", ink: "var(--ink)" },
  success: { surface: "var(--mild-bg)", ink: "var(--mild-fg)" },
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
      className="rounded-row px-4 py-3 text-[0.875rem] leading-6"
      style={{ backgroundColor: style.surface, color: style.ink }}
    >
      {children}
    </div>
  );
}
