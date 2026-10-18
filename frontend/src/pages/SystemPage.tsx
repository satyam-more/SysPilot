import { useState, useRef, useEffect } from "react";
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

export default function SystemPage() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const update = (id: number, patch: Partial<Turn>) =>
    setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, ...patch } : t)));

  const submit = async () => {
    const q = question.trim();
    if (!q || busy) return;
    const id = Date.now();
    setTurns((p) => [...p, { id, question: q, answer: null, tools: [], pending: null, confirmResult: null, error: null, loading: true }]);
    setQuestion("");
    setBusy(true);
    try {
      const r = await sysAPI.ask(q);
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
    try {
      const r = await sysAPI.confirm(pending.pending_id);
      update(turnId, { confirmResult: r.data, pending: null });
    } catch {
      update(turnId, { error: "Could not run the command." });
    } finally {
      setBusy(false);
    }
  };

  const cancel = (turnId: number) => update(turnId, { pending: null });

  return (
    <div className="ask-page">
      {turns.length === 0 && (
        <div className="ask-empty">
          <h2>System Health Assistant</h2>
          <p>
            Ask about your computer: "what's using my memory?", "what starts at
            boot?", "which apps are safe to close?", or "how do I free up disk
            space?". Any command that changes your system is shown for your
            approval before it runs.
          </p>
        </div>
      )}

      <div className="ask-thread">
        {turns.map((turn) => (
          <div key={turn.id} className="ask-turn">
            <div className="ask-question">
              <span className="ask-label">You</span>
              <p>{turn.question}</p>
            </div>
            <div className="ask-answer">
              <span className="ask-label">Assistant</span>
              {turn.loading && (
                <p className="ask-loading"><span className="spinner" /> Checking your system…</p>
              )}
              {turn.error && <p className="ask-error">{turn.error}</p>}
              {turn.answer && <p className="ask-answer-text">{turn.answer}</p>}

              {turn.tools.length > 0 && (
                <div className="ask-evidence">
                  <div className="ask-evidence-header">Tools used</div>
                  {turn.tools.map((t, i) => (
                    <div key={i} className="ask-evidence-item">
                      <span className="src-tag src-filesystem">{t}</span>
                    </div>
                  ))}
                </div>
              )}

              {turn.pending && <ConfirmationGate pending={turn.pending} busy={busy} onConfirm={() => confirm(turn.id, turn.pending!)} onCancel={() => cancel(turn.id)} />}

              {turn.confirmResult && <CommandResult result={turn.confirmResult} />}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="ask-input-bar">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
          placeholder="Ask about your system… (Enter to send)"
          rows={2}
          disabled={busy}
        />
        <button className="btn-primary" onClick={submit} disabled={busy || !question.trim()}>
          {busy ? "…" : "Ask"}
        </button>
      </div>
    </div>
  );
}

function ConfirmationGate({ pending, busy, onConfirm, onCancel }: {
  pending: PendingAction; busy: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  const risky = pending.classification === "approval_required";
  return (
    <div className={`notice ${risky ? "warning" : "success"}`} style={{ marginTop: 14 }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>
        {risky ? "Confirmation required" : "Ready to run"}
      </div>
      <p style={{ marginBottom: 8 }}>{pending.message}</p>
      <code style={{ display: "block", background: "var(--bg)", padding: "8px 12px", borderRadius: 6, marginBottom: 10, fontFamily: "var(--mono)", wordBreak: "break-all" }}>
        {pending.command}
      </code>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn-primary" disabled={busy} onClick={onConfirm}>Run it</button>
        <button className="btn-secondary" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

function CommandResult({ result }: { result: ConfirmResponse }) {
  const ok = result.status === "ok";
  return (
    <div className={`notice ${ok ? "success" : "error"}`} style={{ marginTop: 14 }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>
        {ok ? `Done (exit ${result.exit_code})` : "Failed"}
      </div>
      {result.message && <p>{result.message}</p>}
      {result.stdout && (
        <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, marginTop: 6, maxHeight: 200, overflow: "auto" }}>
          {result.stdout}
        </pre>
      )}
      {result.stderr && (
        <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, color: "var(--danger)", marginTop: 6 }}>
          {result.stderr}
        </pre>
      )}
    </div>
  );
}
