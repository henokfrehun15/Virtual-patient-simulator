const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

const ACCESS_TOKEN_STORAGE_KEY = "vps.access_token";

let accessToken: string | null = window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);

export function setAccessToken(token: string | null): void {
  accessToken = token;
  if (token === null) {
    window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  } else {
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
  }
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (accessToken !== null) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  if (options.body !== undefined && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    let code = "INTERNAL_ERROR";
    let message = "The request failed.";
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } };
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(code, message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
