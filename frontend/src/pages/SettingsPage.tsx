import { useState, useEffect, useCallback } from "react";
import { modelAPI, privacyAPI } from "../api/client";
import type { ModelStatus } from "../api/client";

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
      <PrivacySection />
    </>
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
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("gpt-4o-mini");
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
        text: `Key saved. Masked: ${resp.data.masked_key}`,
      });
      await onUpdate();
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
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </div>
          <div className="form-row">
            <label>Model</label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="e.g. gpt-4o-mini"
            />
          </div>
          <div className="form-row">
            <label>API Key</label>
            <input
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="sk-..."
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
