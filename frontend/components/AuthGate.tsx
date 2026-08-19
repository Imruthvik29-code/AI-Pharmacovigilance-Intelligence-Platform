"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { loadSession } from "@/lib/auth/session";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const session = loadSession();
    if (!session) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        <div className="w-full max-w-xs">
          <LoadingSkeleton label="Checking session" lines={3} />
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
