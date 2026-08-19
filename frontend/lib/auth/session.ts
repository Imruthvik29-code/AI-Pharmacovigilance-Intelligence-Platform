import type { AuthResponse, AuthUser } from "@/lib/api/types";

const SESSION_KEY = "pv.session";

export type Session = {
  accessToken: string;
  tokenType: string;
  expiresIn: number | null;
  user: AuthUser;
};

export function sessionFromAuthResponse(response: AuthResponse): Session {
  return {
    accessToken: response.access_token,
    tokenType: response.token_type || "bearer",
    expiresIn: response.expires_in,
    user: response.user,
  };
}

export function saveSession(session: Session): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function loadSession(): Session | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Session;
    if (!parsed?.accessToken || !parsed.user?.id) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(SESSION_KEY);
}

export function getAccessToken(): string | null {
  return loadSession()?.accessToken ?? null;
}
