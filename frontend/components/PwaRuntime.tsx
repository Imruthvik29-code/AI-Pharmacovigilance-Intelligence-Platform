"use client";

import { useEffect, useLayoutEffect, useState } from "react";
import { PlusIcon } from "@/components/icons/Icons";
import { isCategoryId } from "@/components/patient/categories";

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

declare global {
  interface Window {
    __pvInstallPrompt?: BeforeInstallPromptEvent;
  }
  interface Navigator {
    /** iOS Safari: true when launched from the home screen. */
    standalone?: boolean;
  }
}

/** When the offer was last dismissed, as epoch milliseconds. */
export const INSTALL_DISMISSED_KEY = "pv.installPrompt.dismissedAt";
/** A dismissal keeps the offer away for this long, across navigation and reloads. */
export const INSTALL_SUPPRESS_MS = 24 * 60 * 60 * 1000;
/**
 * Screens that must never scroll. The offer joins them only when it fits in
 * the space they leave; otherwise it waits for the next page that has room.
 */
const NO_SCROLL_SCREEN = ".pv-directory, .pv-overview";
/** On those screens, wait this long without DOM changes before placing it. */
const SETTLE_MS = 400;

function dismissalActive(now = Date.now()): boolean {
  try {
    const stored = Number(window.localStorage.getItem(INSTALL_DISMISSED_KEY));
    return stored > 0 && now - stored < INSTALL_SUPPRESS_MS;
  } catch {
    return false;
  }
}

function runningInstalled(): boolean {
  const standalone =
    typeof window.matchMedia === "function" && window.matchMedia("(display-mode: standalone)").matches;
  return standalone || window.navigator.standalone === true;
}

/**
 * Whether the current page is a no-scroll screen: the patients directory or a
 * patient's overview (a patient page without a detail category). Read from the
 * URL as well as the DOM, so a screen still loading already counts.
 */
function onNoScrollScreen(): boolean {
  if (document.querySelector(NO_SCROLL_SCREEN)) return true;
  const { pathname, search } = window.location;
  if (pathname === "/dashboard") return true;
  return /^\/patients\/[^/]+\/?$/.test(pathname) && !isCategoryId(new URLSearchParams(search).get("category"));
}

/** Identifies the page on screen, including whether it is a no-scroll screen. */
function pageKey(): string {
  return `${window.location.pathname}${window.location.search}|${onNoScrollScreen() ? "fixed" : "flow"}`;
}

export function PwaRuntime() {
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [installed, setInstalled] = useState(false);
  // Held back from a no-scroll screen that has no room for it.
  const [deferred, setDeferred] = useState(false);
  const [noScrollScreen, setNoScrollScreen] = useState(false);
  // A no-scroll screen has stopped rendering, so its height can be trusted.
  const [settled, setSettled] = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }
    setInstalled(runningInstalled());
    setDismissed(dismissalActive());

    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      const promptEvent = event as BeforeInstallPromptEvent;
      window.__pvInstallPrompt = promptEvent;
      setInstallPrompt(promptEvent);
      // A fresh browser offer does not override a recent dismissal.
      setDismissed(dismissalActive());
    };
    const onAppInstalled = () => {
      setInstalled(true);
      setInstallPrompt(null);
      window.__pvInstallPrompt = undefined;
    };

    // A new page (or viewport) is a new chance: re-read the dismissal, which
    // may have expired, and retry an offer held back for lack of room. A page
    // counts as settled once its DOM has been quiet for SETTLE_MS.
    let lastPage = pageKey();
    let frame = 0;
    let quiet = 0;
    const armSettle = () => {
      window.clearTimeout(quiet);
      quiet = window.setTimeout(() => setSettled(true), SETTLE_MS);
    };
    setNoScrollScreen(onNoScrollScreen());
    armSettle();
    const onDomChange = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const page = pageKey();
        if (page !== lastPage) {
          lastPage = page;
          setNoScrollScreen(onNoScrollScreen());
          setSettled(false);
          setDismissed(dismissalActive());
          setDeferred(false);
        }
        armSettle();
      });
    };
    const onResize = () => setDeferred(false);
    const pageWatcher = typeof MutationObserver === "undefined" ? null : new MutationObserver(onDomChange);
    pageWatcher?.observe(document.body, { childList: true, subtree: true });

    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onAppInstalled);
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(quiet);
      pageWatcher?.disconnect();
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onAppInstalled);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  const showing =
    Boolean(installPrompt) && !dismissed && !installed && !deferred && (!noScrollScreen || settled);

  // On a no-scroll screen the offer must fit below the content. Measured after
  // layout and before paint, so an offer that would make the page scroll is
  // withdrawn without ever being seen; it is re-checked if the page grows.
  useLayoutEffect(() => {
    if (!showing) return;
    const check = () => {
      if (!onNoScrollScreen()) return;
      if (document.documentElement.scrollHeight > window.innerHeight + 1) setDeferred(true);
    };
    check();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(check);
    observer.observe(document.body);
    return () => observer.disconnect();
  }, [showing]);

  if (!showing) return null;

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
          try {
            window.localStorage.setItem(INSTALL_DISMISSED_KEY, String(Date.now()));
          } catch {
            /* storage unavailable: the offer still closes for this page */
          }
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
