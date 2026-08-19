"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { loadSession } from "@/lib/auth/session";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace(loadSession() ? "/dashboard" : "/login");
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-xs">
        <LoadingSkeleton label="Loading" lines={3} />
      </div>
    </div>
  );
}
