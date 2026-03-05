// lib/api.ts
// Typed API client. All requests go through this module.
// Token injection and refresh are handled by the axios interceptors.

import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import type {
  TokenResponse, User, Venture, VentureCreateRequest, VenturePatchRequest,
  QueueItem, QueuePatchRequest, PipelineRunRequest, PipelineRunResponse,
  PipelineProgress, AnalyticsSummary,
} from "@/types";

// ── Base client ───────────────────────────────────────────────
export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

// ── Request interceptor — inject Bearer token ─────────────────
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor — handle 401 + silent refresh ────────
let isRefreshing = false;
let refreshQueue: Array<(token: string) => void> = [];

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }
    original._retry = true;

    if (isRefreshing) {
      // Queue this request until the refresh completes
      return new Promise((resolve) => {
        refreshQueue.push((token) => {
          original.headers.Authorization = `Bearer ${token}`;
          resolve(api(original));
        });
      });
    }

    isRefreshing = true;
    try {
      const refreshToken = getRefreshToken();
      if (!refreshToken) throw new Error("No refresh token");

      const { data } = await axios.post<TokenResponse>(
        `${api.defaults.baseURL}/auth/refresh`,
        { refresh_token: refreshToken }
      );

      setTokens(data.access_token, data.refresh_token);
      refreshQueue.forEach((cb) => cb(data.access_token));
      refreshQueue = [];

      original.headers.Authorization = `Bearer ${data.access_token}`;
      return api(original);
    } catch {
      clearTokens();
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
      return Promise.reject(error);
    } finally {
      isRefreshing = false;
    }
  }
);

// ── Token storage ─────────────────────────────────────────────
const ACCESS_KEY  = "ff_access";
const REFRESH_KEY = "ff_refresh";

export function getAccessToken()  { return typeof window !== "undefined" ? localStorage.getItem(ACCESS_KEY)  : null; }
export function getRefreshToken() { return typeof window !== "undefined" ? localStorage.getItem(REFRESH_KEY) : null; }
export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}
export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}
export function isAuthenticated() { return !!getAccessToken(); }

// ── Auth ──────────────────────────────────────────────────────
export const authApi = {
  register: (email: string, password: string) =>
    api.post<TokenResponse>("/auth/register", { email, password }),

  login: (email: string, password: string) =>
    api.post<TokenResponse>("/auth/login", { email, password }),

  me: () => api.get<User>("/auth/me"),
};

// ── Ventures ──────────────────────────────────────────────────
export const venturesApi = {
  list: () =>
    api.get<Venture[]>("/ventures"),

  get: (id: string) =>
    api.get<Venture>(`/ventures/${id}`),

  create: (body: VentureCreateRequest) =>
    api.post<Venture>("/ventures", body),

  patch: (id: string, body: VenturePatchRequest) =>
    api.patch<Venture>(`/ventures/${id}`, body),

  deactivate: (id: string) =>
    api.delete(`/ventures/${id}`),

  inviteMember: (id: string, email: string, role: "operator" | "viewer") =>
    api.post(`/ventures/${id}/members`, { email, role }),
};

// ── Queue ─────────────────────────────────────────────────────
export const queueApi = {
  list: (ventureId: string, params?: { platform?: string; status_filter?: string }) =>
    api.get<QueueItem[]>(`/ventures/${ventureId}/queue`, { params }),

  patch: (ventureId: string, itemId: string, body: QueuePatchRequest) =>
    api.patch<QueueItem>(`/ventures/${ventureId}/queue/${itemId}`, body),
};

// ── Pipeline ──────────────────────────────────────────────────
export const pipelineApi = {
  run: (ventureId: string, body: PipelineRunRequest) =>
    api.post<PipelineRunResponse>(`/ventures/${ventureId}/pipeline/run`, body),

  progress: (ventureId: string, campaignId: number) =>
    api.get<PipelineProgress>(`/ventures/${ventureId}/pipeline/${campaignId}`),

  pulse: (ventureId: string) =>
    api.post(`/ventures/${ventureId}/pulse`),
};

// ── Publish ───────────────────────────────────────────────────
export const publishApi = {
  trigger: (ventureId: string, platform: string) =>
    api.post(`/ventures/${ventureId}/publish/${platform}`),

  runEmail: (ventureId: string) =>
    api.post(`/ventures/${ventureId}/email/run`),

  runSocial: (ventureId: string) =>
    api.post(`/ventures/${ventureId}/social/run`),
};

// ── Analytics ─────────────────────────────────────────────────
export const analyticsApi = {
  summary: (ventureId: string, platform = "youtube") =>
    api.get<AnalyticsSummary>(`/ventures/${ventureId}/analytics`, { params: { platform } }),
};

// ── WebSocket factory ─────────────────────────────────────────
export function createPipelineWs(ventureId: string, campaignId: number): WebSocket {
  const base = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    .replace(/^http/, "ws");
  return new WebSocket(`${base}/ventures/${ventureId}/pipeline/${campaignId}/ws`);
}