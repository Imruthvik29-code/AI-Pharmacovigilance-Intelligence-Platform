export type OAuthProvider = "google" | "azure";

const providerLabels: Record<OAuthProvider, string> = {
  google: "Google",
  azure: "Microsoft",
};

// Supabase publishable credentials are intentionally safe for browser use.
// Environment variables remain the preferred override for other deployments.
const DEFAULT_SUPABASE_URL = "https://icwtuhbhdrpjdtoibxxk.supabase.co";
const DEFAULT_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_2o9Naps4qVN0j_sx6iaKnQ_lZqXNn_E";

export function oauthProviderLabel(provider: OAuthProvider): string {
  return providerLabels[provider];
}

export function startOAuth(provider: OAuthProvider): void {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || DEFAULT_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || DEFAULT_SUPABASE_PUBLISHABLE_KEY;

  const redirectTo = `${window.location.origin}/auth/callback`;
  const url = new URL(`${supabaseUrl.replace(/\/$/, "")}/auth/v1/authorize`);
  url.searchParams.set("provider", provider);
  url.searchParams.set("redirect_to", redirectTo);
  url.searchParams.set("apikey", anonKey);
  if (provider === "azure") url.searchParams.set("scopes", "email");
  window.location.assign(url.toString());
}

export function readOAuthHash(): { accessToken: string; refreshToken: string | null; expiresIn: number | null; tokenType: string } | null {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const accessToken = params.get("access_token");
  if (!accessToken) return null;
  const expiresInRaw = params.get("expires_in");
  return {
    accessToken,
    refreshToken: params.get("refresh_token"),
    expiresIn: expiresInRaw ? Number(expiresInRaw) : null,
    tokenType: params.get("token_type") || "bearer",
  };
}
