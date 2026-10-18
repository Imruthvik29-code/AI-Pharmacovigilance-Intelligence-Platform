import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it, vi } from "vitest";

function worker() {
  const handlers: Record<string, (event: unknown) => void> = {};
  const match = vi.fn().mockResolvedValue({ cached: true });
  const fetch = vi.fn();
  runInNewContext(readFileSync("public/sw.js", "utf8"), {
    URL, fetch, caches: { match },
    self: { location: { origin: "http://127.0.0.1:3000" }, addEventListener: (type: string, fn: (event: unknown) => void) => { handlers[type] = fn; } },
  });
  return { handle: handlers.fetch, match, fetch };
}

describe("service-worker immutable assets", () => {
  it.each([
    "/_next/static/chunks/app/patients/%5BpatientId%5D/page.js",
    "/_next/static/chunks/main-app.js?v=12345",
    "/_next/static/webpack/app/page.aad0c1d97903ee53.hot-update.js",
    "/api/v1/patients/example/analysis",
  ])("leaves mutable development files and clinical API requests to the network: %s", (path) => {
    const w = worker(); const respondWith = vi.fn();
    w.handle({ request: { url: `http://127.0.0.1:3000${path}`, method: "GET" }, respondWith });
    expect(respondWith).not.toHaveBeenCalled();
    expect(w.match).not.toHaveBeenCalled();
  });

  it.each([
    "/_next/static/chunks/app/page-9573ea2d59fe0b61.js",
    "/_next/static/css/6b663762c6f76575.css",
  ])("retains cached immutable production assets: %s", async (path) => {
    const w = worker(); let response: Promise<unknown> | undefined;
    const request = { url: `http://127.0.0.1:3000${path}`, method: "GET" };
    w.handle({ request, respondWith: (value: Promise<unknown>) => { response = value; } });
    expect(await response).toEqual({ cached: true });
    expect(w.match).toHaveBeenCalledWith(request);
    expect(w.fetch).not.toHaveBeenCalled();
  });
});
