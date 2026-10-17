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
async function ensureDevToken(): Promise<void> {
  if (SESSION_TOKEN) return;

  try {
    const resp = await axios.get("http://127.0.0.1:8000/api/dev-token", {
      headers: { Origin: "http://localhost:5173" },
    });
    SESSION_TOKEN = resp.data.token;
  } catch {
    console.warn(
      "TrailBack: could not fetch dev session token. Is the backend running?"
    );
  }
}

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

const api = axios.create({
  baseURL: "http://127.0.0.1:8000",
  headers: { "X-Session-Token": "" },
});

// Inject the session token on every request.
api.interceptors.request.use((config) => {
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

// Initialise dev token if needed (fire and forget in dev mode).
if (!SESSION_TOKEN) {
  ensureDevToken();
}

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

export default api;
