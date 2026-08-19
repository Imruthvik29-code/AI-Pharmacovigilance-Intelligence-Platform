"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { BrandMark } from "@/components/BrandMark";
import { Disclaimer } from "@/components/Disclaimer";
import { StatusBanner } from "@/components/StatusBanner";
import { login } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/errors";
import { usePageTitle } from "@/lib/hooks/usePageTitle";
import { fieldOnCardClass, primaryButtonClass } from "@/lib/ui/classes";

export default function LoginPage() {
  usePageTitle("Login");
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await login({ email: email.trim(), password });
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the API.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-10">
      <div className="mb-6 flex items-center gap-3">
        <BrandMark />
        <div>
          <p className="text-sm font-semibold tracking-tight">Pharmacovigilance Intelligence</p>
          <p className="text-xs text-muted">Medication safety analysis</p>
        </div>
      </div>

      <section className="rounded-2xl border border-line bg-card p-6 shadow-[0_10px_40px_-24px_rgba(20,32,41,0.35)]">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Track medications and run deterministic safety analysis — interactions, ADRs, and a
          composite score, with an optional AI explanation of those findings.
        </p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label className="block text-sm font-medium" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className={fieldOnCardClass}
            />
          </div>
          <div>
            <label className="block text-sm font-medium" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={fieldOnCardClass}
            />
          </div>
          {error ? (
            <StatusBanner tone="error" role="alert">
              {error}
            </StatusBanner>
          ) : null}
          <button type="submit" disabled={submitting} className={`${primaryButtonClass} w-full`}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-5 text-sm text-muted">
          Need an account?{" "}
          <Link href="/signup" className="font-medium text-accent underline-offset-2 hover:underline">
            Create one
          </Link>
        </p>
      </section>

      <footer className="mt-8 px-1">
        <Disclaimer compact />
      </footer>
    </div>
  );
}
