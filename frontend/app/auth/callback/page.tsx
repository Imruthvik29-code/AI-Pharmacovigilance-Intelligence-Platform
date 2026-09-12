"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BrandMark } from "@/components/BrandMark";
import { StatusBanner } from "@/components/StatusBanner";
import { readOAuthHash } from "@/lib/auth/oauth";
import { saveSession } from "@/lib/auth/session";

export default function AuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function complete() {
      const hash = readOAuthHash();
      const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
      const authError = params.get("error_description") || params.get("error");
      window.history.replaceState({}, document.title, "/auth/callback");
      if (authError) {
        if (!cancelled) setError(decodeURIComponent(authError.replace(/\+/g, " ")));
        return;
      }
      if (!hash) {
        if (!cancelled) setError("The sign-in response did not contain a session.");
        return;
      }
      try {
        const response = await fetch("/api/v1/auth/me", { headers: { Authorization: `Bearer ${hash.accessToken}` }, cache: "no-store" });
        if (!response.ok) throw new Error("Could not verify the social sign-in session.");
        const user = (await response.json()) as { id: string; email: string | null };
        saveSession({ accessToken: hash.accessToken, refreshToken: hash.refreshToken, tokenType: hash.tokenType, expiresIn: hash.expiresIn, user });
        if (!cancelled) router.replace("/dashboard");
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not complete social sign-in.");
      }
    }
    void complete();
    return () => { cancelled = true; };
  }, [router]);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-10">
      <div className="mb-6 flex items-center gap-3">
        <BrandMark />
        <div><p className="text-sm font-semibold tracking-tight">Pharmacovigilance Intelligence</p><p className="text-xs text-muted">Completing secure sign-in</p></div>
      </div>
      <section className="rounded-2xl border border-line bg-card p-6 shadow-[0_10px_40px_-24px_rgba(20,32,41,0.35)]">
        {error ? <><StatusBanner tone="error" role="alert">{error}</StatusBanner><a href="/login" className="mt-4 inline-flex min-h-11 items-center justify-center rounded-xl border border-line px-4 text-sm font-medium">Return to sign in</a></> : <div className="text-sm text-muted" aria-live="polite">Verifying your account…</div>}
      </section>
    </main>
  );
}
