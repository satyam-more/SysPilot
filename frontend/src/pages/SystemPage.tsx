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
    // Build conversation history from completed turns so the agent has context.
    const history = turns
      .filter((t) => t.answer)
      .flatMap((t) => [
        { role: "user" as const, content: t.question },
        { role: "assistant" as const, content: t.answer as string },
      ]);
    try {
      const r = await sysAPI.ask(q, history);
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
              {turn.answer && (
                <div className="ask-answer-text markdown">
                  <Markdown remarkPlugins={[remarkGfm]}>{turn.answer}</Markdown>
                </div>
              )}

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
  // Command needs to be run by the user in their own terminal (e.g. sudo).
  if (result.status === "run_in_terminal") {
    const copy = () => navigator.clipboard?.writeText(result.command ?? "");
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
