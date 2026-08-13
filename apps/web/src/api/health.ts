import { request } from "@/api/client";
import type { HealthResponse } from "@/types";

/**
 * /health answers 503 with a body when a dependency is down, so the raw
 * request would throw. Surface the degraded payload instead.
 */
export async function getHealth(): Promise<HealthResponse> {
  try {
    return await request<HealthResponse>("/health");
  } catch (error) {
    if (
      error instanceof Error &&
      "body" in error &&
      typeof error.body === "object" &&
      error.body !== null &&
      "status" in error.body
    ) {
      return error.body as HealthResponse;
    }
    throw error;
  }
}
