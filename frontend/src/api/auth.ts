import { apiFetch, setAccessToken } from "./client";

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export async function register(
  email: string,
  password: string,
  fullName: string | null
): Promise<TokenResponse> {
  const data = await apiFetch<TokenResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, full_name: fullName }),
  });
  setAccessToken(data.access_token);
  return data;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const data = await apiFetch<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setAccessToken(data.access_token);
  return data;
}

export async function refresh(): Promise<TokenResponse> {
  const data = await apiFetch<TokenResponse>("/api/v1/auth/refresh", { method: "POST" });
  setAccessToken(data.access_token);
  return data;
}

export async function fetchMe(): Promise<User> {
  return apiFetch<User>("/api/v1/auth/me");
}

export async function logout(): Promise<void> {
  try {
    await apiFetch<void>("/api/v1/auth/logout", { method: "POST" });
  } finally {
    setAccessToken(null);
  }
}
