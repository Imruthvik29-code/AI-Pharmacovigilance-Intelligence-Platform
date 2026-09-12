"use client";

import { useEffect, useState } from "react";
import { ghostButtonClass, primaryButtonClass } from "@/lib/ui/classes";

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
      className="fixed inset-x-4 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-50 mx-auto flex max-w-xl items-center gap-4 rounded-2xl border border-hairline bg-surface p-4 shadow-[0_18px_50px_rgba(20,32,41,0.14)] sm:inset-x-auto sm:right-6 sm:left-auto"
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-ink">Keep PV Intelligence close</p>
        <p className="mt-0.5 text-xs leading-5 text-ink-2">Install the workspace for quicker access.</p>
      </div>
      <button
        type="button"
        onClick={install}
        className={`${primaryButtonClass} shrink-0`}
      >
        Install
      </button>
      <button
        type="button"
        onClick={() => {
          setDismissed(true);
          window.__pvInstallPrompt = undefined;
        }}
        className={`${ghostButtonClass} shrink-0`}
        aria-label="Dismiss install prompt"
      >
        Not now
      </button>
    </aside>
  );
}
