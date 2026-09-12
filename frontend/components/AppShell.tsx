"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BrandMark } from "@/components/BrandMark";
import { ghostButtonClass } from "@/lib/ui/classes";
import { clearSession, loadSession } from "@/lib/auth/session";

/**
 * `bleed` removes the main gutter so a page can run a surface edge-to-edge
 * (the patient hero). Padded pages keep the default gutter.
 */
export function AppShell({
  children,
  bleed = false,
}: {
  children: React.ReactNode;
  bleed?: boolean;
}) {
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
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:inline-flex focus:min-h-11 focus:items-center focus:rounded-full focus:bg-surface focus:px-5 focus:text-sm focus:font-semibold focus:shadow-[var(--e2)]"
      >
        Skip to content
      </a>
      <header>
        <div className="mx-auto flex max-w-[1160px] items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Link href="/dashboard" className="flex min-h-11 min-w-0 items-center gap-2.5 no-underline">
            <BrandMark size="sm" />
            <span className="min-w-0">
              <span className="block truncate text-[0.875rem] font-semibold tracking-[-0.01em] text-ink sm:hidden">
                PV Intelligence
              </span>
              <span className="hidden text-[0.875rem] font-semibold tracking-[-0.01em] text-ink sm:block">
                Pharmacovigilance Intelligence
              </span>
            </span>
          </Link>
          <div className="flex shrink-0 items-center gap-2 text-sm">
            {email ? (
              <span className="hidden max-w-48 truncate text-[0.8125rem] text-ink-3 md:inline">
                {email}
              </span>
            ) : null}
            <button type="button" onClick={signOut} className={ghostButtonClass}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main
        id="main"
        className={
          bleed
            ? "mx-auto max-w-[1160px] pb-12"
            : "mx-auto max-w-[1160px] px-4 pb-12 pt-2 sm:px-6"
        }
      >
        {children}
      </main>
    </div>
  );
}
