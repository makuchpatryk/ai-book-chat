import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, request } from "@/api/client";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      statusText: "Service Unavailable",
      text: () => Promise.resolve(JSON.stringify(body)),
    }),
  );
}

describe("request", () => {
  it("returns the parsed body on success", async () => {
    stubFetch(200, { status: "ok" });

    await expect(request("/health")).resolves.toEqual({ status: "ok" });
  });

  it("throws a normalized ApiError on failure", async () => {
    stubFetch(503, { detail: "database down" });

    await expect(request("/health")).rejects.toThrow(ApiError);
    await expect(request("/health")).rejects.toThrow("503 database down");
  });
});
