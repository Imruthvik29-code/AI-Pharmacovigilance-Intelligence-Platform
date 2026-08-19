import { clearSession, getAccessToken } from "@/lib/auth/session";
import { ApiError, parseApiDetail } from "@/lib/api/errors";

export const API_PREFIX = "/api/v1";

export type ApiFetchOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  auth?: boolean;
};

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { body, auth = true, headers, ...rest } = options;
  const token = auth ? getAccessToken() : null;

  const requestHeaders = new Headers(headers);
  if (body !== undefined) {
    requestHeaders.set("Content-Type", "application/json");
  }
  if (auth && token) {
    requestHeaders.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_PREFIX}${path}`, {
    ...rest,
    headers: requestHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const payload = await readBody(response);

  if (response.status === 401 && auth) {
    clearSession();
    throw new ApiError(401, parseApiDetail(payload, "Missing or invalid access token."));
  }

  if (!response.ok) {
    throw new ApiError(response.status, parseApiDetail(payload, `Request failed (${response.status}).`));
  }

  return payload as T;
}

export async function apiFetchRaw(
  path: string,
  options: ApiFetchOptions = {},
): Promise<{ status: number; body: unknown }> {
  const { body, auth = true, headers, ...rest } = options;
  const token = auth ? getAccessToken() : null;
  const requestHeaders = new Headers(headers);
  if (body !== undefined) {
    requestHeaders.set("Content-Type", "application/json");
  }
  if (auth && token) {
    requestHeaders.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_PREFIX}${path}`, {
    ...rest,
    headers: requestHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  return { status: response.status, body: await readBody(response) };
}
