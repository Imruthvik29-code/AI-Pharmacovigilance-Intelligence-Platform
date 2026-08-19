"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BrandMark } from "@/components/BrandMark";
import { ghostButtonClass } from "@/lib/ui/classes";
import { clearSession, loadSession } from "@/lib/auth/session";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    setEmail(loadSession()?.user.email ?? null);
  }, []);

  function signOut() {
    clearSession();
    router.replace("/login");
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-card/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
          <Link href="/dashboard" className="flex min-w-0 items-center gap-2.5 no-underline">
            <BrandMark size="sm" />
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold tracking-tight text-ink sm:hidden">
                PV Intelligence
              </span>
              <span className="hidden text-sm font-semibold tracking-tight text-ink sm:block">
                Pharmacovigilance Intelligence
              </span>
            </span>
          </Link>
          <div className="flex shrink-0 items-center gap-2 text-sm">
            {email ? (
              <span className="hidden max-w-48 truncate text-muted md:inline">{email}</span>
            ) : null}
            <button type="button" onClick={signOut} className={ghostButtonClass}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">{children}</main>
    </div>
  );
}
