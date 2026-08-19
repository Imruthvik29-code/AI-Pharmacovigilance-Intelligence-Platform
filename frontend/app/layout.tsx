import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Pharmacovigilance Intelligence",
    template: "%s · Pharmacovigilance Intelligence",
  },
  description:
    "AI-assisted pharmacovigilance platform. Deterministic safety rules produce findings; the LLM explains them when available.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
