"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BrandMark } from "@/components/BrandMark";
import { ghostButtonClass } from "@/lib/ui/classes";
import { clearSession, loadSession } from "@/lib/auth/session";

type AppShellProps = {
  children: React.ReactNode;
  patientExperience?: boolean;
};

function PatientsIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 19.5v-1.25A3.25 3.25 0 0 0 12.75 15h-5.5A3.25 3.25 0 0 0 4 18.25v1.25M10 11.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM17 8h4m-2-2v4" />
    </svg>
  );
}

function SignOutIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.5 8.5 18 12l-3.5 3.5M18 12H8m3.5 7H6.75A2.75 2.75 0 0 1 4 16.25v-8.5A2.75 2.75 0 0 1 6.75 5h4.75" />
    </svg>
  );
}

export function AppShell({ children, patientExperience = false }: AppShellProps) {
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
      <header className={`${patientExperience ? "hidden sm:block" : ""} border-b border-line bg-card/80 backdrop-blur`}>
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
      <main className={`mx-auto max-w-6xl px-4 pt-6 sm:px-6 sm:py-8 ${patientExperience ? "pb-[calc(5.5rem+env(safe-area-inset-bottom))] sm:pb-8" : "pb-6"}`}>
        {children}
      </main>
      {patientExperience ? (
        <nav aria-label="Patient experience" className="fixed inset-x-0 bottom-0 z-50 border-t border-line bg-card/95 pb-[env(safe-area-inset-bottom)] shadow-[0_-8px_28px_rgba(20,32,41,0.08)] backdrop-blur sm:hidden">
          <div className="mx-auto grid h-16 max-w-md grid-cols-2">
            <Link href="/dashboard" className="flex min-h-11 flex-col items-center justify-center gap-1 text-xs font-medium text-accent no-underline">
              <PatientsIcon />
              <span>Patients</span>
            </Link>
            <button type="button" onClick={signOut} className="flex min-h-11 flex-col items-center justify-center gap-1 text-xs font-medium text-muted">
              <SignOutIcon />
              <span>Sign out</span>
            </button>
          </div>
        </nav>
      ) : null}
    </div>
  );
}
