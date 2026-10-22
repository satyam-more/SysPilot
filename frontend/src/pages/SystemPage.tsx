import { useState, useRef, useEffect } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { sysAPI } from "../api/client";
import type { PendingAction, ConfirmResponse } from "../api/client";

interface Turn {
  id: number;
  question: string;
  answer: string | null;
  tools: string[];
  pending: PendingAction | null;
  confirmResult: ConfirmResponse | null;
  error: string | null;
  loading: boolean;
}

interface Session {
  id: string;
  title: string;
  createdAt: number;
  turns: Turn[];
}

const SESSIONS_KEY = "syspilot:sessions";
const ACTIVE_KEY = "syspilot:active-session";

const newId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

function makeSession(): Session {
  return { id: newId(), title: "New chat", createdAt: Date.now(), turns: [] };
}

// Load saved sessions from localStorage. Transient per-turn fields (loading,
// pending actions) aren't meaningful across reloads, so reset them.
function loadSessions(): Session[] {
  try {
    const raw = localStorage.getItem(SESSIONS_KEY);
    if (!raw) return [];
    const saved = JSON.parse(raw) as Session[];
    if (!Array.isArray(saved)) return [];
    return saved.map((s) => ({
      ...s,
      turns: (s.turns ?? []).map((t) => ({ ...t, loading: false, pending: null })),
    }));
  } catch {
    return [];
  }
}

export default function SystemPage({ onOpenSettings }: { onOpenSettings?: () => void }) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  // Voice mode simulates the Alexa+ experience: answers come back short and
  // spoken-style (no tables), the way they'd be read aloud by a voice assistant.
  const [voiceMode, setVoiceMode] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // --- Multi-session (ChatGPT-style) state ---------------------------------
  const [sessions, setSessions] = useState<Session[]>(() => {
    const loaded = loadSessions();
    return loaded.length ? loaded : [makeSession()];
  });
  const [activeId, setActiveId] = useState<string>(() => {
    const saved = localStorage.getItem(ACTIVE_KEY);
    const loaded = loadSessions();
    if (saved && loaded.some((s) => s.id === saved)) return saved;
    return loaded[0]?.id ?? "";
  });

  // Ensure activeId always points at an existing session.
  const active = sessions.find((s) => s.id === activeId) ?? sessions[0];
  const turns = active?.turns ?? [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  // Persist sessions + active selection so chats survive reloads/restarts.
  useEffect(() => {
    try {
      localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
    } catch {
      /* storage full or unavailable — non-fatal */
    }
  }, [sessions]);

  useEffect(() => {
    if (activeId) localStorage.setItem(ACTIVE_KEY, activeId);
  }, [activeId]);

  // Patch the turns of the active session.
  const setTurns = (updater: (prev: Turn[]) => Turn[]) =>
    setSessions((prev) =>
      prev.map((s) => (s.id === active.id ? { ...s, turns: updater(s.turns) } : s))
    );

  const update = (id: number, patch: Partial<Turn>) =>
    setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, ...patch } : t)));

  // --- Session management ---------------------------------------------------
  const newChat = () => {
    // Reuse an existing empty session if the current one is already blank.
    const empty = sessions.find((s) => s.turns.length === 0);
    if (empty) {
      setActiveId(empty.id);
    } else {
      const s = makeSession();
      setSessions((prev) => [s, ...prev]);
      setActiveId(s.id);
    }
    setQuestion("");
  };

  const selectChat = (id: string) => {
    if (busy) return;
    setActiveId(id);
  };

  const deleteChat = (id: string) => {
    setSessions((prev) => {
      const remaining = prev.filter((s) => s.id !== id);
      const next = remaining.length ? remaining : [makeSession()];
      if (id === activeId) setActiveId(next[0].id);
      return next;
    });
  };

  const submit = async () => {
    const q = question.trim();
    if (!q || busy) return;
    const id = Date.now();
    const isFirst = turns.length === 0;
    setTurns((p) => [...p, { id, question: q, answer: null, tools: [], pending: null, confirmResult: null, error: null, loading: true }]);
    // Title the chat from its first question (ChatGPT-style).
    if (isFirst) {
      const title = q.length > 40 ? q.slice(0, 40).trimEnd() + "…" : q;
      setSessions((prev) => prev.map((s) => (s.id === active.id ? { ...s, title } : s)));
    }
    setQuestion("");
    setBusy(true);
    // Build conversation history from completed turns so the agent has context.
    const history = turns
      .filter((t) => t.answer)
      .flatMap((t) => [
        { role: "user" as const, content: t.question },
        { role: "assistant" as const, content: t.answer as string },
      ]);
    // In voice mode, ask the agent to respond the way Alexa+ would speak it:
    // a couple of short sentences, plain spoken language, no tables or markdown.
    const sent = voiceMode
      ? `${q}\n\n(Respond as a voice assistant would speak aloud: 2-3 short sentences, plain spoken language, no tables, lists, or markdown.)`
      : q;
    try {
      const r = await sysAPI.ask(sent, history);
      update(id, {
        answer: r.data.answer,
        tools: r.data.tool_calls.map((t) => t.tool),
        pending: r.data.pending_action,
        loading: false,
      });
    } catch (err: any) {
      update(id, { error: err.response?.data?.detail ?? "Request failed.", loading: false });
    } finally {
      setBusy(false);
    }
  };

  const confirm = async (turnId: number, pending: PendingAction) => {
    setBusy(true);
    const turn = turns.find((t) => t.id === turnId);
    try {
      const r = await sysAPI.confirm(pending.pending_id, turn?.question ?? "");
      update(turnId, { confirmResult: r.data, pending: null });
    } catch {
      update(turnId, { error: "Could not run the command." });
    } finally {
      setBusy(false);
    }
  };

  const cancel = (turnId: number) => update(turnId, { pending: null });

  const SUGGESTIONS = [
    "Is my computer healthy?",
    "What's slowing down my computer?",
    "Which apps can I safely close?",
    "How do I free up space?",
  ];

  const ask = (q: string) => {
    setQuestion(q);
    setTimeout(() => submit(), 0);
  };

  return (
    <div className="cgpt-layout">
      <aside className="cgpt-sidebar">
        <button className="cgpt-newchat" onClick={newChat}>
          <span className="cgpt-plus">+</span> New chat
        </button>
        <div className="cgpt-session-list">
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`cgpt-session ${s.id === active?.id ? "active" : ""}`}
              onClick={() => selectChat(s.id)}
            >
              <span className="cgpt-session-icon">💬</span>
              <span className="cgpt-session-title">{s.title}</span>
              <button
                className="cgpt-session-del"
                title="Delete chat"
                onClick={(e) => { e.stopPropagation(); deleteChat(s.id); }}
              >
                🗑
              </button>
            </div>
          ))}
        </div>
        <div className="cgpt-sidebar-foot">
          <button className="cgpt-settings-btn" onClick={onOpenSettings}>
            <span>⚙</span> Settings
          </button>
          <div className="cgpt-brand">SysPilot</div>
        </div>
      </aside>

      <div className="chat">
      {turns.length === 0 ? (
        <div className="welcome">
          <div className="welcome-icon">🩺</div>
          <h2>How can I help with your computer?</h2>
          <p>Ask in plain words — I'll check your system and explain it simply. Nothing changes without your approval.</p>
          <div className="suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="suggestion-chip" onClick={() => ask(s)}>
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="chat-thread">
          {turns.map((turn) => (
            <div key={turn.id} className="chat-turn">
              <div className="msg msg-user">
                <div className="msg-bubble">{turn.question}</div>
                <div className="msg-avatar user">You</div>
              </div>

              <div className="msg msg-assistant">
                <div className="msg-avatar bot">🩺</div>
                <div className="msg-content">
                  {turn.loading && (
                    <div className="msg-bubble bot">
                      <span className="spinner" /> Checking your system…
                    </div>
                  )}
                  {turn.error && <div className="msg-bubble bot error-text">{turn.error}</div>}
                  {turn.answer && (
                    <div className="msg-bubble bot markdown">
                      <Markdown remarkPlugins={[remarkGfm]}>{turn.answer}</Markdown>
                    </div>
                  )}
                  {turn.pending && (
                    <ConfirmationGate
                      pending={turn.pending}
                      busy={busy}
                      onConfirm={() => confirm(turn.id, turn.pending!)}
                      onCancel={() => cancel(turn.id)}
                    />
                  )}
                  {turn.confirmResult && <CommandResult result={turn.confirmResult} />}
                </div>
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      <div className={`composer ${voiceMode ? "voice-on" : ""}`}>
        <button
          className={`composer-mic ${voiceMode ? "on" : ""}`}
          onClick={() => setVoiceMode((v) => !v)}
          title={voiceMode ? "Voice mode on (Alexa+ style answers)" : "Turn on voice mode (Alexa+ style)"}
          aria-pressed={voiceMode}
          aria-label="Toggle voice mode"
        >
          🎙
        </button>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
          placeholder={voiceMode ? "Ask Alexa+ about your computer…" : "Ask about your computer…"}
          rows={1}
          disabled={busy}
        />
        <button className="composer-send" onClick={submit} disabled={busy || !question.trim()} aria-label="Send">
          {busy ? "…" : "↑"}
        </button>
      </div>
      </div>
    </div>
  );
}

function ConfirmationGate({ pending, busy, onConfirm, onCancel }: {
  pending: PendingAction; busy: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <div className="action-card" style={{ marginTop: 12 }}>
      <div className="action-head">
        <span className="action-icon">⚡</span>
        <span>Needs your OK to continue</span>
      </div>
      <details className="action-cmd">
        <summary>View the exact command</summary>
        <code>{pending.command}</code>
      </details>
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button className="btn-primary" disabled={busy} onClick={onConfirm}>Allow</button>
        <button className="btn-secondary" disabled={busy} onClick={onCancel}>Not now</button>
      </div>
    </div>
  );
}

function CommandResult({ result }: { result: ConfirmResponse }) {
  // Command needs to be run by the user in their own terminal (e.g. sudo).
  if (result.status === "run_in_terminal") {
    // Use a textarea + execCommand fallback: navigator.clipboard triggers a
    // Qt permission request that crashes the pywebview desktop window.
    const copy = () => {
      const cmd = result.command ?? "";
      try {
        const ta = document.createElement("textarea");
        ta.value = cmd;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      } catch {
        /* no-op */
      }
    };
    return (
      <div className="notice warning" style={{ marginTop: 14 }}>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>Run this in your terminal</div>
        {result.message && <p style={{ marginBottom: 8 }}>{result.message}</p>}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <code style={{ flex: 1, background: "var(--bg)", padding: "8px 12px", borderRadius: 6, fontFamily: "var(--mono)", wordBreak: "break-all" }}>
            {result.command}
          </code>
          <button className="btn-secondary" style={{ flexShrink: 0 }} onClick={copy}>
            Copy
          </button>
        </div>
      </div>
    );
  }

  const ok = result.status === "ok";
  return (
    <div className={`notice ${ok ? "success" : "error"}`} style={{ marginTop: 14 }}>
      {ok ? (
        <>
          {/* Hero: the plain-language insight is the main content. */}
          {result.insight ? (
            <div className="markdown" style={{ fontSize: 15, lineHeight: 1.6 }}>
              <Markdown remarkPlugins={[remarkGfm]}>{result.insight}</Markdown>
            </div>
          ) : (
            <p>Done.</p>
          )}

          {/* Raw output is hidden by default — only shown if the user opens it. */}
          {result.stdout && (
            <details style={{ marginTop: 12 }}>
              <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--text-muted)", opacity: 0.7 }}>
                Technical details (raw output)
              </summary>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, marginTop: 8, maxHeight: 220, overflow: "auto", opacity: 0.85 }}>
                {result.stdout}
              </pre>
            </details>
          )}
        </>
      ) : (
        <>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Failed</div>
          {result.message && <p>{result.message}</p>}
          {result.stderr && (
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, color: "var(--danger)", marginTop: 6 }}>
              {result.stderr}
            </pre>
          )}
        </>
      )}
    </div>
  );
}
