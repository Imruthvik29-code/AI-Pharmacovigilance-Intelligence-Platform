"use client";

import { useEffect, useState } from "react";
import { PlusIcon } from "@/components/icons/Icons";

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

declare global {
  interface Window {
    __pvInstallPrompt?: BeforeInstallPromptEvent;
  }
}

export function PwaRuntime() {
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }

    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      const promptEvent = event as BeforeInstallPromptEvent;
      window.__pvInstallPrompt = promptEvent;
      setInstallPrompt(promptEvent);
      setDismissed(false);
    };

    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
  }, []);

  if (!installPrompt || dismissed) return null;

  async function install() {
    const promptEvent = installPrompt;
    if (!promptEvent) return;

    await promptEvent.prompt();
    await promptEvent.userChoice;
    setInstallPrompt(null);
    window.__pvInstallPrompt = undefined;
  }

  return (
    <aside
      aria-label="Install PV Intelligence"
      className="fixed inset-x-4 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-50 mx-auto flex max-w-xl items-center gap-3 rounded-2xl border border-hairline bg-surface py-3 pl-4 pr-12 shadow-[0_18px_50px_rgba(20,32,41,0.14)] sm:inset-x-auto sm:right-6 sm:left-auto"
    >
      <div className="min-w-0 flex-1">
        <p className="text-[0.875rem] font-semibold leading-5 text-ink">Install PV Intelligence</p>
        <p className="text-sm leading-5 text-ink-2">Get quicker access.</p>
      </div>
      <button
        type="button"
        onClick={install}
        className="on-dark inline-flex min-h-11 shrink-0 items-center justify-center rounded-full bg-cta px-4 text-sm font-semibold text-white transition hover:-translate-y-px"
      >
        Install
      </button>
      {/* A small visible × in the top-right corner; the button itself keeps a
          44px square hit area anchored to that corner. */}
      <button
        type="button"
        onClick={() => {
          setDismissed(true);
          window.__pvInstallPrompt = undefined;
        }}
        className="absolute right-0 top-0 h-11 w-11 text-ink-2"
        aria-label="Dismiss install prompt"
      >
        <span
          aria-hidden="true"
          className="absolute right-2.5 top-2.5 flex h-6 w-6 items-center justify-center rounded-full bg-surface-2"
        >
          <PlusIcon className="h-3.5 w-3.5 rotate-45" />
        </span>
      </button>
    </aside>
  );
}
