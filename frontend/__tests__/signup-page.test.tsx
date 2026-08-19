import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SignupPage from "@/app/signup/page";
import { loadSession } from "@/lib/auth/session";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

describe("signup page 202 recovery", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("keeps the form usable after email confirmation is required", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 202,
        text: async () =>
          JSON.stringify({
            detail: "Signup succeeded but requires email confirmation before login.",
          }),
      }),
    );

    render(<SignupPage />);
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "long-enough");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText(/email confirmation/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /return to sign in/i })).toHaveAttribute(
      "href",
      "/login",
    );
    expect(loadSession()).toBeNull();
    expect(screen.getByRole("button", { name: "Create account" })).toBeEnabled();

    await user.clear(screen.getByLabelText("Email"));
    await user.type(screen.getByLabelText("Email"), "other@example.com");
    expect(screen.getByLabelText("Email")).toHaveValue("other@example.com");
    expect(screen.getByRole("button", { name: "Create account" })).toBeEnabled();
  });
});
