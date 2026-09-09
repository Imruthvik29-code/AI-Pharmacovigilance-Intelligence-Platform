import { describe, expect, it } from "vitest";
import { oauthProviderLabel, readOAuthHash } from "@/lib/auth/oauth";

describe("oauth helpers", () => {
  it("uses clear provider labels", () => {
    expect(oauthProviderLabel("google")).toBe("Google");
    expect(oauthProviderLabel("azure")).toBe("Microsoft");
  });

  it("reads the Supabase implicit-flow session from the URL fragment", () => {
    window.location.hash = "#access_token=access-123&refresh_token=refresh-123&expires_in=3600&token_type=bearer";
    expect(readOAuthHash()).toEqual({
      accessToken: "access-123",
      refreshToken: "refresh-123",
      expiresIn: 3600,
      tokenType: "bearer",
    });
    window.history.replaceState({}, "", "/");
  });
});
