import { useState, useEffect, useCallback } from "react";
import { modelAPI, privacyAPI, trackingAPI, browsersAPI } from "../api/client";
import type {
  ModelStatus,
  TrackingStatus,
  BrowserStatus,
} from "../api/client";

// Models available per provider. Keep in sync with SUPPORTED_PROVIDERS
// in backend/harness/providers/provider_registry.py.
const PROVIDER_MODELS: Record<string, string[]> = {
  groq: [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
  ],
  openai: ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
};

export default function SettingsPage() {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const resp = await modelAPI.getStatus();
      setStatus(resp.data);
      setError(null);
    } catch (err) {
      setError("Could not reach backend. Is it running on port 8000?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  if (loading) {
    return <div className="card"><p>Loading settings...</p></div>;
  }

  return (
    <>
      {error && <div className="notice error">{error}</div>}
      <ModelModeSection status={status} onUpdate={fetchStatus} />
      <ApiKeySection status={status} onUpdate={fetchStatus} />
      <TrackingSection />
      <BrowsersSection />
      <PrivacySection />
    </>
  );
}

// ---------------------------------------------------------------------------
// Browser History Tracking
// ---------------------------------------------------------------------------

function BrowsersSection() {
  const [status, setStatus] = useState<BrowserStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [domainsText, setDomainsText] = useState("");
  const [saved, setSaved] = useState(false);

  const refresh = async () => {
    try {
      const resp = await browsersAPI.getStatus();
      setStatus(resp.data);
      setDomainsText(resp.data.excluded_domains.join("\n"));
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const toggleBrowser = async (name: string, enable: boolean) => {
    if (!status) return;
    const current = status.browsers.filter((b) => b.enabled).map((b) => b.name);
    const next = enable
      ? [...current, name]
      : current.filter((n) => n !== name);
    setBusy(true);
    try {
      await browsersAPI.setEnabled(next);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const saveDomains = async () => {
    setBusy(true);
    setSaved(false);
    try {
      const domains = domainsText
        .split("\n")
        .map((d) => d.trim())
        .filter(Boolean);
      await browsersAPI.setExcludedDomains(domains);
      setSaved(true);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const browsers = status?.browsers ?? [];
  const running = status?.collector === "running";

  return (
    <div className="card">
      <h2>Browser History</h2>
      <p style={{ marginBottom: 12, color: "var(--text-muted)" }}>
        TrailBack can read your browser history to remember pages you visited.
        Nothing is sent anywhere — it reads the local history file only for
        browsers you enable below.
      </p>

      {browsers.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
          No supported browsers detected on this machine.
        </p>
      ) : (
        <>
          <div style={{ marginBottom: 14 }}>
            {browsers.map((b) => (
              <label
                key={b.name}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "8px 0",
                  borderBottom: "1px solid var(--border)",
                  fontSize: 14,
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={b.enabled}
                  disabled={busy}
                  onChange={(e) => toggleBrowser(b.name, e.target.checked)}
                  style={{ width: "auto" }}
                />
                <span>{b.name}</span>
                {b.enabled && running && (
                  <span className="status-badge online" style={{ marginLeft: "auto" }}>
                    <span className="status-dot" />
                    Tracking
                  </span>
                )}
              </label>
            ))}
          </div>

          <div className="form-row">
            <label>Excluded domains (one per line — never recorded)</label>
            <textarea
              value={domainsText}
              onChange={(e) => {
                setDomainsText(e.target.value);
                setSaved(false);
              }}
              rows={4}
              placeholder="mail.google.com&#10;web.whatsapp.com"
              style={{ fontFamily: "var(--mono)", fontSize: 13 }}
            />
          </div>
          <div className="form-actions">
            <button className="btn-primary" disabled={busy} onClick={saveDomains}>
              Save exclusions
            </button>
            {saved && (
              <span style={{ color: "var(--success)", fontSize: 13, alignSelf: "center" }}>
                Saved
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Activity Tracking
// ---------------------------------------------------------------------------

function TrackingSection() {
  const [status, setStatus] = useState<TrackingStatus | null>(null);
  const [newPath, setNewPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const resp = await trackingAPI.getStatus();
      setStatus(resp.data);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const addDir = async () => {
    const p = newPath.trim();
    if (!p) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await trackingAPI.addDirectory(p);
      setStatus(resp.data);
      setNewPath("");
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Could not add directory.");
    } finally {
      setBusy(false);
    }
  };

  const removeDir = async (path: string) => {
    setBusy(true);
    setError(null);
    try {
      const resp = await trackingAPI.removeDirectory(path);
      setStatus(resp.data);
    } catch {
      setError("Could not remove directory.");
    } finally {
      setBusy(false);
    }
  };

  const running = status?.collector === "running";
  const dirs = status?.watched_directories ?? [];

  return (
    <div className="card">
      <h2>Activity Tracking</h2>
      <p style={{ marginBottom: 12, color: "var(--text-muted)" }}>
        TrailBack records file activity in the folders below. Nothing is
        recorded in folders you don't add here.
      </p>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <span className={`status-badge ${running ? "online" : "offline"}`}>
          <span className="status-dot" />
          {running ? "Watching" : dirs.length ? "Idle" : "No folders"}
        </span>
        {running && (
          <span style={{ color: "var(--text-muted)", fontSize: 13 }}>
            {dirs.length} folder{dirs.length === 1 ? "" : "s"} tracked
          </span>
        )}
      </div>

      {error && <div className="notice error">{error}</div>}

      {dirs.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          {dirs.map((d) => (
            <div
              key={d}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 0",
                borderBottom: "1px solid var(--border)",
                fontSize: 13,
              }}
            >
              <span style={{ fontFamily: "var(--mono)", wordBreak: "break-all" }}>
                {d}
              </span>
              <button
                className="btn-secondary"
                style={{ padding: "4px 10px", fontSize: 12 }}
                disabled={busy}
                onClick={() => removeDir(d)}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="form-row">
        <label>Add a folder to track</label>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            value={newPath}
            onChange={(e) => setNewPath(e.target.value)}
            placeholder="/home/you/projects/my-app"
            style={{ flex: 1 }}
            onKeyDown={(e) => e.key === "Enter" && addDir()}
          />
          <button className="btn-primary" disabled={busy || !newPath.trim()} onClick={addDir}>
            Add
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Model Mode Selector
// ---------------------------------------------------------------------------

function ModelModeSection({
  status,
  onUpdate,
}: {
  status: ModelStatus | null;
  onUpdate: () => void;
}) {
  const [switching, setSwitching] = useState(false);

  const setMode = async (mode: "offline" | "api") => {
    setSwitching(true);
    try {
      await modelAPI.setMode(mode);
      await onUpdate();
    } catch {
      // error handled by parent refresh
    } finally {
      setSwitching(false);
    }
  };

  const mode = status?.mode ?? "offline";
  const connected = status?.connected ?? false;

  return (
    <div className="card">
      <h2>Model Mode</h2>

      <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <button
          className={mode === "offline" ? "btn-primary" : "btn-secondary"}
          disabled={switching}
          onClick={() => setMode("offline")}
        >
          Offline (Ollama)
        </button>
        <button
          className={mode === "api" ? "btn-primary" : "btn-secondary"}
          disabled={switching}
          onClick={() => setMode("api")}
        >
          API Provider
        </button>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className={`status-badge ${connected ? "online" : "offline"}`}>
          <span className="status-dot" />
          {connected ? "Connected" : "Disconnected"}
        </span>
        {status?.model && (
          <span style={{ color: "var(--text-muted)", fontSize: 13 }}>
            Model: {status.model}
          </span>
        )}
        {status?.error && (
          <span style={{ color: "var(--danger)", fontSize: 13 }}>
            {status.error}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// API Key Form
// ---------------------------------------------------------------------------

function ApiKeySection({
  status,
  onUpdate,
}: {
  status: ModelStatus | null;
  onUpdate: () => void;
}) {
  const [provider, setProvider] = useState("groq");
  const [model, setModel] = useState<string>(PROVIDER_MODELS.groq[0]);
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "warning" | "error"; text: string } | null>(null);

  const keyConfigured = status?.key_configured ?? false;
  const keyPersistent = status?.key_persistent ?? false;

  const saveKey = async () => {
    if (!key.trim()) return;
    setSaving(true);
    setMessage(null);
    try {
      const resp = await modelAPI.saveApiKey(provider, model, key);
      setKey("");
      setMessage({
        type: "success",
        text: `Key saved (${resp.data.masked_key}). Switched to API mode. Testing connection…`,
      });
      await onUpdate();
      // Auto-verify the key works right after saving.
      try {
        const test = await modelAPI.testConnection();
        if (test.data.success) {
          setMessage({
            type: "success",
            text: `Connected to ${test.data.model}. API mode is active.`,
          });
        } else {
          setMessage({
            type: "error",
            text: test.data.error ?? "Key saved but connection test failed.",
          });
        }
      } catch {
        /* status refresh already done */
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail ?? "Failed to save key.";
      setMessage({ type: "error", text: detail });
    } finally {
      setSaving(false);
    }
  };

  const deleteKey = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await modelAPI.deleteApiKey();
      setMessage({ type: "success", text: "API key removed." });
      await onUpdate();
    } catch {
      setMessage({ type: "error", text: "Failed to delete key." });
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    setTesting(true);
    setMessage(null);
    try {
      const resp = await modelAPI.testConnection();
      if (resp.data.success) {
        setMessage({
          type: "success",
          text: `Connection successful — model: ${resp.data.model}`,
        });
      } else {
        setMessage({
          type: "error",
          text: resp.data.error ?? "Connection failed.",
        });
      }
    } catch (err: any) {
      setMessage({
        type: "error",
        text: err.response?.data?.detail ?? "Could not test connection.",
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="card">
      <h2>API Key</h2>

      {keyConfigured && !keyPersistent && (
        <div className="notice warning">
          API key is stored in memory only and will be lost when TrailBack
          restarts. This usually means your OS keyring is unavailable.
        </div>
      )}

      {message && <div className={`notice ${message.type}`}>{message.text}</div>}

      {keyConfigured ? (
        <>
          <p style={{ marginBottom: 12, color: "var(--text-muted)" }}>
            An API key is configured.
          </p>
          <div className="form-actions">
            <button
              className="btn-secondary"
              disabled={testing}
              onClick={testConnection}
            >
              {testing ? "Testing..." : "Test Connection"}
            </button>
            <button
              className="btn-danger"
              disabled={saving}
              onClick={deleteKey}
            >
              Remove Key
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="form-row">
            <label>Provider</label>
            <select
              value={provider}
              onChange={(e) => {
                const p = e.target.value;
                setProvider(p);
                // Reset model to the new provider's first option.
                setModel(PROVIDER_MODELS[p][0]);
              }}
            >
              <option value="groq">Groq (free)</option>
              <option value="openai">OpenAI</option>
            </select>
          </div>
          <div className="form-row">
            <label>Model</label>
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {PROVIDER_MODELS[provider].map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <label>API Key</label>
            <input
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder={provider === "groq" ? "gsk_..." : "sk-..."}
            />
          </div>
          <div className="form-actions">
            <button
              className="btn-primary"
              disabled={saving || !key.trim()}
              onClick={saveKey}
            >
              {saving ? "Saving..." : "Save Key"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Privacy Toggle
// ---------------------------------------------------------------------------

function PrivacySection() {
  const [privacyState, setPrivacyState] = useState<"active" | "paused">("active");
  const [toggling, setToggling] = useState(false);

  useEffect(() => {
    privacyAPI.status().then((r) => setPrivacyState(r.data.state)).catch(() => {});
  }, []);

  const toggle = async () => {
    setToggling(true);
    try {
      if (privacyState === "active") {
        await privacyAPI.pause();
        setPrivacyState("paused");
      } else {
        await privacyAPI.resume();
        setPrivacyState("active");
      }
    } catch {
      // ignore
    } finally {
      setToggling(false);
    }
  };

  return (
    <div className="card">
      <h2>Privacy Mode</h2>
      <p style={{ marginBottom: 12, color: "var(--text-muted)" }}>
        When active, all event collection is paused. Existing data is not
        deleted but no new events are recorded.
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span className={`status-badge ${privacyState === "paused" ? "error" : "online"}`}>
          <span className="status-dot" />
          {privacyState === "paused" ? "Paused" : "Active"}
        </span>
        <button
          className={privacyState === "active" ? "btn-danger" : "btn-primary"}
          disabled={toggling}
          onClick={toggle}
        >
          {privacyState === "active" ? "Pause Recording" : "Resume Recording"}
        </button>
      </div>
    </div>
  );
}
