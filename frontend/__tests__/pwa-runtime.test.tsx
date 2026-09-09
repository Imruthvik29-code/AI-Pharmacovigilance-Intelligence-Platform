import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PwaRuntime } from "@/components/PwaRuntime";

describe("PwaRuntime", () => {
  const originalServiceWorker = navigator.serviceWorker;

  beforeEach(() => {
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { register: vi.fn().mockResolvedValue(undefined) },
    });
    window.__pvInstallPrompt = undefined;
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
});
