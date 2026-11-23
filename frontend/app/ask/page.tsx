"use client";

import { useState } from "react";
import { Cites } from "@/components/Cites";
import { NoticeCard } from "@/components/NoticeCard";
import { SourcesPanel } from "@/components/SourcesPanel";
import { ask } from "@/lib/api";
import type { AnswerSentence, AskAnswer } from "@/lib/types";

const VERDICT: Record<string, { text: string; cls: string; help: string }> = {
  supported: { text: "Supported", cls: "verdict-supported", help: "The cited passage supports this sentence." },
  partially_supported: { text: "Partially supported", cls: "verdict-partial", help: "The cited passage supports only part of this sentence." },
  not_supported: { text: "Not supported", cls: "verdict-not", help: "The cited passage does not support this sentence." },
  unsupported_citation: {
    text: "Unsupported citation",
    cls: "verdict-bad-cite",
    help: "The citation does not exist in the Act version for this tax year, or was not among the passages retrieved.",
  },
};

const STATUS: Record<string, string> = {
  answered: "Answered: every sentence is supported by its citation.",
  partially_verified: "Partially verified: some sentences are not fully supported. They are shown, marked, not hidden.",
  declined: "Declined",
};

function SentenceRow({ s }: { s: AnswerSentence }) {
  const v = VERDICT[s.verdict] ?? { text: s.verdict, cls: "", help: "" };
  return (
    <li className={`sentence ${v.cls}`}>
      <div>{s.text}</div>
      <div className="sentence-meta">
        <span className={`badge ${v.cls}`} title={v.help}>{v.text}</span>
        {s.chunk_ids.length > 0 ? <Cites list={s.chunk_ids} /> : <span className="muted small">no resolved citation</span>}
      </div>
      {s.reason && <div className="muted small">{s.reason}</div>}
      {s.stage1_problems.length > 0 && (
        <div className="small">Citation check: {s.stage1_problems.join("; ")}</div>
      )}
    </li>
  );
}

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [taxYear, setTaxYear] = useState("2026");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setAnswer(await ask(question.trim(), Number(taxYear)));
    } catch (err) {
      setAnswer(null);
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const cited = answer ? [...new Set(answer.sentences.flatMap((s) => s.chunk_ids))] : [];

  return (
    <div>
      <h1>Ask a question</h1>
      <form className="panel" onSubmit={submit}>
        <p className="muted" style={{ marginTop: 0 }}>
          Answers come only from the curated corpus for the chosen tax year. Each sentence is checked twice: does the cited
          provision exist in the right Act, and does the passage support the sentence?
        </p>
        <div className="grid">
          <label>Tax year
            <select value={taxYear} onChange={(e) => setTaxYear(e.target.value)}>
              <option value="2025">FY 2025-26 (Income-tax Act 1961)</option>
              <option value="2026">Tax Year 2026-27 (Income-tax Act 2025)</option>
            </select>
          </label>
        </div>
        <label style={{ marginTop: 12 }}>Question
          <textarea
            rows={3}
            maxLength={1000}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. What is the receipts limit for presumptive taxation of an IT consultant?"
          />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="actions">
          <button type="submit" disabled={busy || question.trim().length < 3}>{busy ? "Retrieving, drafting and checking…" : "Ask"}</button>
        </div>
      </form>

      {answer && (
        <section aria-live="polite">
          <h2>Answer</h2>
          <div className="panel">
            <p style={{ marginTop: 0 }}>
              <span className={`badge status-${answer.status}`}>{STATUS[answer.status] ?? answer.status}</span>{" "}
              <span className="muted small">{answer.act_id} · model {answer.model || "—"} · retrieval similarity {answer.retrieval_similarity}</span>
            </p>

            {answer.premise_issue && (
              <div className="flag high">
                <strong>Premise correction:</strong> {answer.premise_issue}
              </div>
            )}

            {answer.status === "declined" ? (
              <p>{answer.decline_reason}</p>
            ) : (
              <ol className="sentences">
                {answer.sentences.map((s, k) => <SentenceRow key={k} s={s} />)}
              </ol>
            )}
          </div>

          {answer.notices.length > 0 && (
            <>
              <h2>Interpretation uncertain</h2>
              {answer.notices.map((n) => <NoticeCard key={n.assumption_id} notice={n} />)}
            </>
          )}

          <SourcesPanel ids={cited} notices={[]} />
          {answer.passages.length > 0 && (
            <p className="muted small">Passages shown to the model: {answer.passages.join(", ")}</p>
          )}
        </section>
      )}
    </div>
  );
}
