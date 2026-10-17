import { useState, useRef, useEffect } from "react";
import { askAPI } from "../api/client";
import type { AskResponse } from "../api/client";

interface Turn {
  id: number;
  question: string;
  answer: string | null;
  evidence: AskResponse["evidence"];
  iterations: number;
  error: string | null;
  loading: boolean;
}

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const submit = async () => {
    const q = question.trim();
    if (!q || busy) return;

    const turnId = Date.now();
    setTurns((prev) => [
      ...prev,
      {
        id: turnId,
        question: q,
        answer: null,
        evidence: [],
        iterations: 0,
        error: null,
        loading: true,
      },
    ]);
    setQuestion("");
    setBusy(true);

    try {
      const resp = await askAPI.ask(q);
      setTurns((prev) =>
        prev.map((t) =>
          t.id === turnId
            ? {
                ...t,
                answer: resp.data.answer,
                evidence: resp.data.evidence,
                iterations: resp.data.iterations,
                loading: false,
              }
            : t
        )
      );
    } catch (err: any) {
      const status = err.response?.status;
      let msg = "Something went wrong. Please try again.";
      if (status === 403) {
        msg =
          err.response?.data?.detail ??
          "Privacy mode is active, or the session is invalid.";
      } else if (status === 500) {
        msg =
          err.response?.data?.detail ??
          "The model could not be reached. Check your provider in Settings.";
      } else if (err.response?.data?.detail) {
        msg = err.response.data.detail;
      }
      setTurns((prev) =>
        prev.map((t) =>
          t.id === turnId ? { ...t, error: msg, loading: false } : t
        )
      );
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter inserts a newline.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="ask-page">
      {turns.length === 0 && (
        <div className="ask-empty">
          <h2>Ask about your activity</h2>
          <p>
            Ask questions like "What was I working on yesterday?" or "Where did
            I leave off in my Rust project?" TrailBack searches your recorded
            activity and answers with evidence.
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
              <span className="ask-label">TrailBack</span>
              {turn.loading && (
                <p className="ask-loading">
                  <span className="spinner" /> Searching your activity…
                </p>
              )}
              {turn.error && <p className="ask-error">{turn.error}</p>}
              {turn.answer && (
                <>
                  <p className="ask-answer-text">{turn.answer}</p>
                  {turn.evidence.length > 0 && (
                    <div className="ask-evidence">
                      <div className="ask-evidence-header">
                        Evidence ({turn.evidence.length})
                      </div>
                      {turn.evidence.map((e) => (
                        <div key={e.event_id} className="ask-evidence-item">
                          <span className={`src-tag src-${e.source}`}>
                            {e.source}
                          </span>
                          <span className="ask-evidence-title">
                            {e.title || e.event_type}
                          </span>
                          {e.content_excerpt && (
                            <span className="ask-evidence-excerpt">
                              {e.content_excerpt}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="ask-input-bar">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about your activity… (Enter to send, Shift+Enter for newline)"
          rows={2}
          disabled={busy}
        />
        <button
          className="btn-primary"
          onClick={submit}
          disabled={busy || !question.trim()}
        >
          {busy ? "Thinking…" : "Ask"}
        </button>
      </div>
    </div>
  );
}
