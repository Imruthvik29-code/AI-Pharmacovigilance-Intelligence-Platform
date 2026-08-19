import { beforeEach, describe, expect, it, vi } from "vitest";
import { signup } from "@/lib/api/auth";
import { loadSession } from "@/lib/auth/session";

describe("signup client", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("treats HTTP 202 as confirmation-required and does not authenticate", async () => {
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

    const result = await signup({ email: "new@example.com", password: "long-enough" });
    expect(result.kind).toBe("confirmation_required");
    if (result.kind === "confirmation_required") {
      expect(result.detail).toMatch(/email confirmation/i);
    }
    expect(loadSession()).toBeNull();
  });
});
