import { apiFetch, apiFetchRaw } from "@/lib/api/client";
import { ApiError, parseApiDetail } from "@/lib/api/errors";
import type { AuthResponse, AuthUser, LoginRequest, SignupRequest } from "@/lib/api/types";
import { saveSession, sessionFromAuthResponse, type Session } from "@/lib/auth/session";

export type SignupResult =
  | { kind: "authenticated"; session: Session }
  | { kind: "confirmation_required"; detail: string };

export async function login(payload: LoginRequest): Promise<Session> {
  const response = await apiFetch<AuthResponse>("/auth/login", {
    method: "POST",
    auth: false,
    body: payload,
  });
  const session = sessionFromAuthResponse(response);
  saveSession(session);
  return session;
}

export async function signup(payload: SignupRequest): Promise<SignupResult> {
  const { status, body } = await apiFetchRaw("/auth/signup", {
    method: "POST",
    auth: false,
    body: payload,
  });

  if (status === 202) {
    return {
      kind: "confirmation_required",
      detail: parseApiDetail(
        body,
        "Signup succeeded but requires email confirmation before login.",
      ),
    };
  }

  if (status >= 400) {
    throw new ApiError(status, parseApiDetail(body, "Signup request could not be completed."));
  }

  const response = body as AuthResponse;
  if (!response?.access_token) {
    return {
      kind: "confirmation_required",
      detail: "Signup succeeded but requires email confirmation before login.",
    };
  }

  const session = sessionFromAuthResponse(response);
  saveSession(session);
  return { kind: "authenticated", session };
}

export async function getMe(): Promise<AuthUser> {
  return apiFetch<AuthUser>("/auth/me", { method: "GET" });
}
