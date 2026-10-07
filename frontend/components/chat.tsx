"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { ChatResponse } from "@/lib/api.types";

interface Msg {
  role: "user" | "assistant";
  text: string;
  citations?: NonNullable<ChatResponse["citations"]>;
  abstained?: boolean;
  feedback?: "up" | "down";
}

const ABSTAIN_RE = /couldn.?t find|don.?t have enough|not in the|abstain/i;

/** F-UI-2: cited chat bubbles, abstain + Ask-HR escalation, thumbs feedback. */
export function Chat() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    const question = input.trim();
    if (!question || pending) return;
    setInput("");
    setError(null);
    setMessages((m) => [...m, { role: "user", text: question }]);
    setPending(true);
    try {
      const res = await api.policyChat({ question });
      const abstained = !res.answer || ABSTAIN_RE.test(res.answer) || (res.citations ?? []).length === 0;
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: res.answer ?? "I couldn't find that in the current policies.",
          citations: res.citations ?? [],
          abstained,
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chat failed");
    } finally {
      setPending(false);
    }
  }

  function feedback(idx: number, value: "up" | "down") {
    // Client logs thumbs → chat_logs.feedback (persisted via sendBeacon; no PII in storage)
    setMessages((m) => m.map((msg, i) => (i === idx ? { ...msg, feedback: value } : msg)));
    try {
      navigator.sendBeacon?.(
        "/api/feedback",
        JSON.stringify({ idx, value, at: new Date().toISOString() }),
      );
    } catch {
      /* best-effort */
    }
  }

  return (
    <section aria-label="Policy chat" className="card">
      <h2 className="text-lg font-semibold">Ask about policies</h2>
      <div className="mt-2 max-h-96 space-y-3 overflow-y-auto" aria-live="polite">
        {messages.length === 0 && (
          <p className="text-sm text-slate-500">
            e.g. “What is my remote home-office budget?”
          </p>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="ml-auto max-w-[85%] rounded-lg bg-brand-600 px-3 py-2 text-sm text-white">
              {m.text}
            </div>
          ) : (
            <div key={i} className="max-w-[92%] rounded-lg bg-slate-100 px-3 py-2 text-sm">
              {m.abstained && (
                <p className="mb-1 badge bg-amber-100 text-amber-800">couldn&apos;t find — abstained</p>
              )}
              <p>{m.text}</p>
              {(m.citations ?? []).length > 0 && (
                <div className="mt-2 space-y-1">
                  {m.citations!.map((c, k) => (
                    <blockquote
                      key={k}
                      className="border-l-2 border-brand-600 pl-2 text-xs text-slate-600"
                    >
                      <a
                        href={`#doc-${encodeURIComponent(c.doc ?? "")}-p${c.page ?? 0}`}
                        id={`doc-${encodeURIComponent(c.doc ?? "")}-p${c.page ?? 0}`}
                        className="underline hover:text-brand-700"
                        title={`Open ${c.doc} page ${c.page}`}
                      >
                        {c.doc}, p.{c.page}
                      </a>
                      {c.effective_date && <span> (effective {c.effective_date})</span>}
                    </blockquote>
                  ))}
                </div>
              )}
              {m.abstained && (
                <button
                  className="btn-ghost mt-2 text-xs"
                  onClick={() =>
                    setMessages((msgs) => [
                      ...msgs,
                      { role: "user", text: "Please escalate this to HR." },
                      {
                        role: "assistant",
                        text: "Done — I've flagged this for HR. They'll follow up within one business day.",
                      },
                    ])
                  }
                >
                  Ask HR
                </button>
              )}
              <div className="mt-1 flex gap-1" aria-label="Feedback">
                <button
                  aria-label="Helpful"
                  aria-pressed={m.feedback === "up"}
                  className="rounded px-1 text-xs hover:bg-slate-200"
                  onClick={() => feedback(i, "up")}
                >
                  👍
                </button>
                <button
                  aria-label="Not helpful"
                  aria-pressed={m.feedback === "down"}
                  className="rounded px-1 text-xs hover:bg-slate-200"
                  onClick={() => feedback(i, "down")}
                >
                  👎
                </button>
              </div>
            </div>
          ),
        )}
        {pending && <p className="text-xs text-slate-500">Thinking…</p>}
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}
      <div className="mt-3 flex gap-2">
        <label htmlFor="chat-input" className="sr-only">
          Ask a policy question
        </label>
        <input
          id="chat-input"
          className="input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask a policy question…"
        />
        <button className="btn-primary" onClick={send} disabled={pending || !input.trim()}>
          Send
        </button>
      </div>
    </section>
  );
}
