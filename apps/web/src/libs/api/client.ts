/** Thin fetch wrapper. Vite proxies /api -> FastAPI in dev. */

export const API_BASE = "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/** Parse the body (tolerating non-JSON, e.g. a proxy's HTML 502) and throw ApiError on failure. */
export async function readResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!response.ok) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(response.status, `${response.status} ${detail}`, body);
  }

  return body as T;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  return readResponse<T>(response);
}

export async function upload<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body,
  });
  return readResponse<T>(response);
}
