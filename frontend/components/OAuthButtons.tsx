"use client";

import { useState } from "react";
import { oauthProviderLabel, startOAuth, type OAuthProvider } from "@/lib/auth/oauth";
import { StatusBanner } from "@/components/StatusBanner";

const providers: OAuthProvider[] = ["google", "azure"];

function ProviderIcon({ provider }: { provider: OAuthProvider }) {
  if (provider === "google") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none">
        <path d="M21.35 12.27c0-.72-.06-1.42-.18-2.09H12v3.96h5.24a4.48 4.48 0 0 1-1.94 2.94v2.45h3.14c1.84-1.69 2.91-4.18 2.91-7.26Z" fill="#4285F4" />
        <path d="M12 21.72c2.63 0 4.84-.87 6.45-2.36l-3.14-2.45c-.87.58-1.98.92-3.31.92-2.54 0-4.69-1.72-5.46-4.03H3.29v2.53A9.74 9.74 0 0 0 12 21.72Z" fill="#34A853" />
        <path d="M6.54 13.8A5.85 5.85 0 0 1 6.24 12c0-.62.11-1.23.3-1.8V7.67H3.29A9.73 9.73 0 0 0 2.25 12c0 1.57.38 3.05 1.04 4.33l3.25-2.53Z" fill="#FBBC05" />
        <path d="M12 6.17c1.43 0 2.71.49 3.72 1.45l2.79-2.79C16.83 3.3 14.63 2.28 12 2.28a9.74 9.74 0 0 0-8.71 5.39l3.25 2.53C7.31 7.89 9.46 6.17 12 6.17Z" fill="#EA4335" />
      </svg>
    );
  }

  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5">
      <rect x="3" y="3" width="8" height="8" fill="#F25022" />
      <rect x="13" y="3" width="8" height="8" fill="#7FBA00" />
      <rect x="3" y="13" width="8" height="8" fill="#00A4EF" />
      <rect x="13" y="13" width="8" height="8" fill="#FFB900" />
    </svg>
  );
}

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
      <div className="relative flex items-center py-1.5">
        <div className="h-px flex-1 bg-line" />
        <span className="px-3 text-[10px] font-medium uppercase tracking-[0.16em] text-muted">or</span>
        <div className="h-px flex-1 bg-line" />
      </div>
      <div className="mt-2 flex justify-center gap-2">
        {providers.map((provider) => (
          <button
            key={provider}
            type="button"
            onClick={() => handleSignIn(provider)}
            disabled={loading !== null}
            aria-label={`Continue with ${oauthProviderLabel(provider)}`}
            title={`Continue with ${oauthProviderLabel(provider)}`}
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-line bg-card text-ink transition hover:border-accent hover:bg-paper disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading === provider ? <span className="text-xs" aria-hidden="true">…</span> : <ProviderIcon provider={provider} />}
          </button>
        ))}
      </div>
      {error ? <div className="mt-3"><StatusBanner tone="error" role="alert">{error}</StatusBanner></div> : null}
      <p className="mt-2 text-center text-[11px] leading-5 text-muted">Sign in securely with your Google or Microsoft account.</p>
    </div>
  );
}
