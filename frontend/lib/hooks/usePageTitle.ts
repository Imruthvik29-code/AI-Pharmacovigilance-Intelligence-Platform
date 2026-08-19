"use client";

import { useEffect } from "react";

const ROOT = "Pharmacovigilance Intelligence";

export function usePageTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · ${ROOT}`;
    return () => {
      document.title = ROOT;
    };
  }, [title]);
}
