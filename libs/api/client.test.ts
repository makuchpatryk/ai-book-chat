import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, request, upload } from "@/api/client";

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

describe("upload", () => {
  it("sends FormData without JSON content-type", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      statusText: "Created",
      text: () => Promise.resolve(JSON.stringify({ id: "doc-1" })),
    });
    vi.stubGlobal("fetch", mockFetch);

    const formData = new FormData();
    await upload("/documents", formData);

    const callArg = mockFetch.mock.calls[0]?.[1];
    expect(callArg).not.toHaveProperty("headers.Content-Type");
  });

  it("throws ApiError on failure", async () => {
    stubFetch(413, { detail: "file too large" });

    const formData = new FormData();
    await expect(upload("/documents", formData)).rejects.toThrow(ApiError);
    await expect(upload("/documents", formData)).rejects.toThrow("413 file too large");
  });
});
