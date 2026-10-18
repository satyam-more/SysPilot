/**
 * TrailBack API client.
 *
 * Session token is read from the <meta name="tb-session"> tag injected by
 * the backend into the served HTML. It is never stored in localStorage
 * or sessionStorage — the token lives only in this module-level variable.
 *
 * In dev mode (vite dev server at port 5173), the meta tag is empty.
 * The client fetches a dev token from the backend's /api/dev-token endpoint
 * at startup. This token is only used in dev mode.
 */

import axios from "axios";

// ---------------------------------------------------------------------------
// Session token
// ---------------------------------------------------------------------------

function readSessionToken(): string {
  const meta = document.querySelector<HTMLMetaElement>(
    'meta[name="tb-session"]'
  );
  return meta?.content ?? "";
}

let SESSION_TOKEN = readSessionToken();

// In dev mode, the meta tag is empty (vite serves index.html directly,
// not through the backend). Fetch a dev token from the backend.
// tokenReady resolves once the token is available (or failed). Every
// outbound request awaits this so no request fires with an empty token.
async function ensureDevToken(): Promise<void> {
  if (SESSION_TOKEN) return;

  try {
    // In dev mode, request goes through Vite proxy to backend.
    const resp = await axios.get("/api/dev-token");
    SESSION_TOKEN = resp.data.token;
  } catch {
    console.warn(
      "TrailBack: could not fetch dev session token. Is the backend running?"
    );
  }
}

// Kick off token fetch immediately and keep the promise so requests can await it.
const tokenReady: Promise<void> = SESSION_TOKEN
  ? Promise.resolve()
  : ensureDevToken();

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

// Use empty baseURL in dev mode so requests go through the Vite proxy
// (vite.config.ts proxies /api → http://127.0.0.1:8000).
// In production, the backend serves the frontend and same-origin applies.
const API_BASE = import.meta.env.DEV ? "" : "";

const api = axios.create({
  baseURL: API_BASE,
  headers: { "X-Session-Token": "" },
});

// Inject the session token on every request.
// Await tokenReady first so the very first request still carries the token
// in dev mode (avoids a startup race that would trigger a false 403).
api.interceptors.request.use(async (config) => {
  await tokenReady;
  config.headers["X-Session-Token"] = SESSION_TOKEN;
  return config;
});

// Handle 403 — session expired or unauthorized.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 403) {
      window.dispatchEvent(new CustomEvent("trailback:session-expired"));
    }
    return Promise.reject(error);
  }
);

// (token fetch already started above via tokenReady)

// ---------------------------------------------------------------------------
// Typed API methods
// ---------------------------------------------------------------------------

export interface ModelStatus {
  mode: "offline" | "api";
  model: string;
  connected: boolean;
  error: string | null;
  key_configured: boolean;
  key_persistent: boolean;
}

export interface ProviderInfo {
  name: string;
  models: string[];
}

export const modelAPI = {
  getStatus: () => api.get<ModelStatus>("/api/model/status"),
  setMode: (mode: "offline" | "api") =>
    api.post("/api/model/mode", { mode }),
  saveApiKey: (provider: string, model: string, key: string) =>
    api.post<{ status: string; masked_key: string }>("/api/model/api-key", {
      provider,
      model,
      key,
    }),
  deleteApiKey: () => api.delete("/api/model/api-key"),
  testConnection: () =>
    api.post<{ success: boolean; model: string; error: string | null }>(
      "/api/model/test-connection"
    ),
  getProviders: () => api.get<ProviderInfo[]>("/api/model/providers"),
};

export interface PrivacyStatus {
  state: "active" | "paused";
  collectors: Record<string, string>;
}

export const privacyAPI = {
  pause: () => api.post("/api/privacy/pause"),
  resume: () => api.post("/api/privacy/resume"),
  status: () => api.get<PrivacyStatus>("/api/privacy/status"),
};

export interface AskResponse {
  answer: string;
  evidence: Array<{
    event_id: string;
    source: string;
    event_type: string;
    title: string | null;
    timestamp: string;
    content_excerpt: string | null;
  }>;
  iterations: number;
  tool_calls_made: number;
}

export const askAPI = {
  ask: (question: string, contextHint?: object) =>
    api.post<AskResponse>("/api/ask", { question, context_hint: contextHint }),
};

export interface PendingAction {
  pending_id: string;
  command: string;
  classification: "read_only" | "approval_required" | "deny";
  message: string;
}

export interface SysAskResponse {
  answer: string;
  tool_calls: Array<{ tool: string; input: Record<string, unknown> }>;
  pending_action: PendingAction | null;
  iterations: number;
}

export interface ConfirmResponse {
  status: "ok" | "error";
  command?: string;
  exit_code?: number;
  stdout?: string;
  stderr?: string;
  message?: string;
}

export const sysAPI = {
  ask: (question: string) =>
    api.post<SysAskResponse>("/api/sys/ask", { question }),
  confirm: (pending_id: string) =>
    api.post<ConfirmResponse>("/api/sys/confirm", { pending_id }),
};

export interface TrackingStatus {
  collector: "running" | "stopped";
  watched_directories: string[];
  excluded_folders: string[];
  excluded_extensions: string[];
}

export const trackingAPI = {
  getStatus: () => api.get<TrackingStatus>("/api/tracking/status"),
  addDirectory: (path: string) =>
    api.post<TrackingStatus>("/api/tracking/directories", { path }),
  removeDirectory: (path: string) =>
    api.delete<TrackingStatus>("/api/tracking/directories", { data: { path } }),
  start: () => api.post("/api/tracking/start"),
  stop: () => api.post("/api/tracking/stop"),
};

export interface BrowserInfo {
  name: string;
  path: string;
  kind: "chromium" | "firefox";
  enabled: boolean;
}

export interface BrowserStatus {
  collector: "running" | "stopped";
  browsers: BrowserInfo[];
  excluded_domains: string[];
}

export const browsersAPI = {
  getStatus: () => api.get<BrowserStatus>("/api/browsers/status"),
  setEnabled: (names: string[]) =>
    api.post<{ status: string; enabled: string[]; collector: string }>(
      "/api/browsers/enabled",
      { names }
    ),
  setExcludedDomains: (domains: string[]) =>
    api.post<{ status: string; excluded_domains: string[] }>(
      "/api/browsers/excluded-domains",
      { domains }
    ),
  start: () => api.post("/api/browsers/start"),
  stop: () => api.post("/api/browsers/stop"),
};

export default api;
