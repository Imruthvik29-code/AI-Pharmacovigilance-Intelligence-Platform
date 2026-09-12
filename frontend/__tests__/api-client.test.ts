import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch, apiFetchRaw } from "@/lib/api/client";
import { loadSession, saveSession } from "@/lib/auth/session";

describe("api client", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("prevents authenticated responses from being persisted in browser caches", async () => {
    saveSession({
      accessToken: "token-123",
      tokenType: "bearer",
      expiresIn: 3600,
      user: { id: "user-1", email: "analyst@example.com" },
    });

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ id: "patient-1" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch<{ id: string }>("/patients/patient-1", { method: "GET" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.cache).toBe("no-store");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer token-123");
  });

  it("clears the session when an authenticated request is rejected with 401", async () => {
    saveSession({
      accessToken: "expired-token",
      tokenType: "bearer",
      expiresIn: 3600,
      user: { id: "user-1", email: "analyst@example.com" },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        text: async () => JSON.stringify({ detail: "Token expired." }),
      }),
    );

    await expect(apiFetch("/auth/me", { method: "GET" })).rejects.toMatchObject({
      status: 401,
      detail: "Token expired.",
    });
    expect(loadSession()).toBeNull();
  });

  it("clears the session after a raw authenticated request receives 401", async () => {
    saveSession({
      accessToken: "expired-token",
      tokenType: "bearer",
      expiresIn: 3600,
      user: { id: "user-1", email: "analyst@example.com" },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        text: async () => JSON.stringify({ detail: "Token expired." }),
      }),
    );

    const response = await apiFetchRaw("/some/raw-endpoint", { method: "GET" });

    expect(response.status).toBe(401);
    expect(loadSession()).toBeNull();
  });
});
