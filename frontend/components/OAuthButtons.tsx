"use client";

import { useState } from "react";
import { oauthProviderLabel, startOAuth, type OAuthProvider } from "@/lib/auth/oauth";
import { secondaryButtonClass } from "@/lib/ui/classes";
import { StatusBanner } from "@/components/StatusBanner";

const providers: OAuthProvider[] = ["google", "azure"];

export function OAuthButtons() {
  const [loading, setLoading] = useState<OAuthProvider | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleSignIn(provider: OAuthProvider) {
    if (loading) return;
    setLoading(provider);
    setError(null);
    try {
      startOAuth(provider);
    } catch (err) {
      setLoading(null);
      setError(err instanceof Error ? err.message : "Social sign-in is unavailable.");
    }
  }

  return (
    <div className="mt-5">
      <div className="relative flex items-center py-2">
        <div className="h-px flex-1 bg-line" />
        <span className="px-3 text-[10px] font-medium uppercase tracking-[0.16em] text-muted">or continue with</span>
        <div className="h-px flex-1 bg-line" />
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {providers.map((provider) => (
          <button key={provider} type="button" onClick={() => handleSignIn(provider)} disabled={loading !== null} className={`${secondaryButtonClass} min-h-11 w-full justify-center bg-card`}>
            {loading === provider ? "Redirecting…" : `Continue with ${oauthProviderLabel(provider)}`}
          </button>
        ))}
      </div>
      {error ? <div className="mt-3"><StatusBanner tone="error" role="alert">{error}</StatusBanner></div> : null}
      <p className="mt-2 text-center text-[11px] leading-5 text-muted">Social sign-in uses the configured Supabase identity provider. Your password is never sent to this app.</p>
    </div>
  );
}
