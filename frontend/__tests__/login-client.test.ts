import { beforeEach, describe, expect, it, vi } from "vitest";
import { login } from "@/lib/api/auth";
import { loadSession } from "@/lib/auth/session";

describe("login client", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("posts credentials to /api/v1/auth/login and stores the access token", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          access_token: "token-123",
          refresh_token: "unused-refresh",
          token_type: "bearer",
          expires_in: 3600,
          user: { id: "user-1", email: "analyst@example.com" },
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const session = await login({ email: "analyst@example.com", password: "secret-password" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/login");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      email: "analyst@example.com",
      password: "secret-password",
    });
    expect(session.accessToken).toBe("token-123");
    expect(loadSession()?.accessToken).toBe("token-123");
    expect(loadSession()?.user.email).toBe("analyst@example.com");
  });

  it("surfaces backend login errors without inventing a session", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        text: async () => JSON.stringify({ detail: "Invalid email or password." }),
      }),
    );

    await expect(login({ email: "a@b.com", password: "nope" })).rejects.toMatchObject({
      status: 401,
      detail: "Invalid email or password.",
    });
    expect(loadSession()).toBeNull();
  });
});
