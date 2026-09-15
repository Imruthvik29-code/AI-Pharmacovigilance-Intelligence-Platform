import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { INSTALL_DISMISSED_KEY, INSTALL_SUPPRESS_MS, PwaRuntime } from "@/components/PwaRuntime";

describe("PwaRuntime", () => {
  const originalServiceWorker = navigator.serviceWorker;

  beforeEach(() => {
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { register: vi.fn().mockResolvedValue(undefined) },
    });
    window.__pvInstallPrompt = undefined;
    // Dismissals now persist; keep each test starting from a clean slate.
    window.localStorage.clear();
  });

  afterEach(() => {
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: originalServiceWorker,
    });
    window.__pvInstallPrompt = undefined;
  });

  it("registers the service worker on mount", async () => {
    const register = navigator.serviceWorker.register as ReturnType<typeof vi.fn>;
    render(<PwaRuntime />);

    await waitFor(() => expect(register).toHaveBeenCalledWith("/sw.js"));
  });

  it("offers installation when the browser provides an install prompt", async () => {
    const user = userEvent.setup();
    const prompt = vi.fn().mockResolvedValue(undefined);
    const userChoice = Promise.resolve({ outcome: "accepted" as const });
    render(<PwaRuntime />);

    const event = new Event("beforeinstallprompt") as Event & {
      prompt: () => Promise<void>;
      userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
    };
    event.prompt = prompt;
    event.userChoice = userChoice;
    window.dispatchEvent(event);

    expect(await screen.findByRole("button", { name: "Install" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Install" }));

    await waitFor(() => expect(prompt).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Install" })).not.toBeInTheDocument());
    expect(window.__pvInstallPrompt).toBeUndefined();
  });

  it("lets the user dismiss the install prompt", async () => {
    const user = userEvent.setup();
    render(<PwaRuntime />);

    const event = new Event("beforeinstallprompt") as Event & {
      prompt: () => Promise<void>;
      userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
    };
    event.prompt = vi.fn().mockResolvedValue(undefined);
    event.userChoice = Promise.resolve({ outcome: "dismissed" as const });
    window.dispatchEvent(event);

    expect(await screen.findByRole("button", { name: "Install" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Dismiss install prompt" }));

    expect(screen.queryByRole("button", { name: "Install" })).not.toBeInTheDocument();
    expect(window.__pvInstallPrompt).toBeUndefined();
  });

  it("shows the compact offer with a single install action and an icon dismiss control", async () => {
    const user = userEvent.setup();
    const prompt = vi.fn().mockResolvedValue(undefined);
    render(<PwaRuntime />);

    const event = new Event("beforeinstallprompt") as Event & {
      prompt: () => Promise<void>;
      userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
    };
    event.prompt = prompt;
    event.userChoice = Promise.resolve({ outcome: "dismissed" as const });
    window.dispatchEvent(event);

    const offer = await screen.findByRole("complementary", { name: "Install PV Intelligence" });
    expect(offer).toHaveTextContent("Install PV Intelligence");
    expect(screen.getByText("Get quicker access.")).toBeInTheDocument();
    expect(screen.queryByText("Not now")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Dismiss install prompt" }));

    expect(screen.queryByRole("complementary", { name: "Install PV Intelligence" })).not.toBeInTheDocument();
    expect(prompt).not.toHaveBeenCalled();
  });

  function offerInstall() {
    const event = new Event("beforeinstallprompt") as Event & {
      prompt: () => Promise<void>;
      userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
    };
    event.prompt = vi.fn().mockResolvedValue(undefined);
    event.userChoice = Promise.resolve({ outcome: "dismissed" as const });
    window.dispatchEvent(event);
  }

  it("remembers a dismissal across remounts instead of offering again on the next page", async () => {
    const user = userEvent.setup();
    const first = render(<PwaRuntime />);
    offerInstall();
    await user.click(await screen.findByRole("button", { name: "Dismiss install prompt" }));

    const stored = Number(window.localStorage.getItem(INSTALL_DISMISSED_KEY));
    expect(stored).toBeGreaterThan(0);
    expect(Date.now() - stored).toBeLessThan(5000);

    first.unmount();
    render(<PwaRuntime />);
    offerInstall();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole("complementary", { name: "Install PV Intelligence" })).not.toBeInTheDocument();
  });

  it("offers installation again once the dismissal is older than a day", async () => {
    window.localStorage.setItem(INSTALL_DISMISSED_KEY, String(Date.now() - INSTALL_SUPPRESS_MS - 1000));
    render(<PwaRuntime />);
    offerInstall();
    expect(await screen.findByRole("complementary", { name: "Install PV Intelligence" })).toBeInTheDocument();
  });

  it("stays hidden when the app is already running installed", async () => {
    const original = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === "(display-mode: standalone)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })) as unknown as typeof window.matchMedia;
    try {
      render(<PwaRuntime />);
      offerInstall();
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(screen.queryByRole("complementary", { name: "Install PV Intelligence" })).not.toBeInTheDocument();
    } finally {
      window.matchMedia = original;
    }
  });
});
