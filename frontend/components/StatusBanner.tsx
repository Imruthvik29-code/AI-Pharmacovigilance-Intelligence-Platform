type Tone = "error" | "info" | "success";

const tones: Record<Tone, string> = {
  error: "border-high/30 bg-[#fdf2f4] text-high",
  info: "border-line bg-[#eef4f3] text-ink",
  success: "border-low/25 bg-[#eef7f4] text-low",
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
  return (
    <div role={role} className={`rounded-lg border px-3 py-2.5 text-sm leading-6 ${tones[tone]}`}>
      {children}
    </div>
  );
}
