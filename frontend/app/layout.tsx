import type { Metadata, Viewport } from "next";
import { PwaRuntime } from "@/components/PwaRuntime";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Pharmacovigilance Intelligence",
    template: "%s · Pharmacovigilance Intelligence",
  },
  description:
    "AI-assisted pharmacovigilance platform. Deterministic safety rules produce findings; the LLM explains them when available.",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/icon.svg",
    apple: "/icon.svg",
  },
};

export const viewport: Viewport = {
  themeColor: "#123c3a",
  colorScheme: "light",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
        <PwaRuntime />
      </body>
    </html>
  );
}
