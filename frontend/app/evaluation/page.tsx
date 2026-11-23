"use client";

import { useEffect, useState } from "react";

// Phase H results as stored by scripts/run_evaluation.py (GET /evaluation). Nothing is computed here.
type Counts = { pass: number; n: number; rate: number | null };
type Retrieval = {
  n: number;
  overall: Record<string, number>;
  by_category: Record<string, Record<string, number>>;
  wrong_act_returned: string[];
  misses_at_5: { id: string; q: string }[];
};
type Judge = {
  n: number;
  accuracy: number;
  false_support_rate: number | null;
  missed_support_rate: number | null;
  errors: { id: string; kind: string; label: string; verdict: string }[];
  stage1_violations: string[];
};
type Rag = {
  faithfulness: { sentences: number; supported: number; rate: number | null };
  key_fact_cases: number;
  key_fact_relevance: number | null;
  context_recall_cases: number;
  context_recall: number | null;
  judge_vs_hand_check?: { status: string; n: number; agreement?: number | null; false_support_rate?: number | null; negatives?: number };
};
type Pair<T> = { metric: string; original: T | null; heldout: T | null; note?: string };
type Summary = {
  date: string;
  git_commit: string;
  model: string;
  embedding_model: string;
  corpus: { chunks_on_disk: number; chunks_in_index: number | string };
  heldout: { frozen_at: string; written_by: string };
  counts: Record<string, unknown>;
  requests: { sent: number; cache_hits: number };
  slices: {
    arithmetic: { metric: string; personas: number; personas_all_match: number; figures: number; matched: number; note: string;
      by_persona: { id: string; title: string; figures: number; matched: number }[] };
    tax_year_retrieval: Pair<Retrieval>;
    temporal_traps?: Pair<{ "retrieval_hit@3": number | null; retrieval_n: number; wrong_act_returned: number; answers: Counts }>;
    false_premise?: Pair<Counts>;
    wrong_jurisdiction?: Pair<Counts>;
    out_of_scope?: Pair<Counts>;
    contested_interpretation?: Pair<Counts>;
    citation_verification?: Pair<Judge>;
    rag_quality?: Pair<Rag>;
  };
  known_failures?: { set: string; kind: string; id: string; slice?: string; q?: string; problems?: string[]; label?: string; verdict?: string }[];
};

const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 1000) / 10}%`);
const frac = (c: Counts | null | undefined) => (c && c.n ? `${c.pass}/${c.n}` : "–");

function Row({ name, metric, original, heldout }: { name: string; metric: string; original: string; heldout: string }) {
  return (
    <tr>
      <th scope="row">{name}</th>
      <td className="small">{metric}</td>
      <td>{original}</td>
      <td>{heldout}</td>
    </tr>
  );
}

function Results({ s }: { s: Summary }) {
  const sl = s.slices;
  const r = sl.tax_year_retrieval;
  const t = sl.temporal_traps;
  const cv = sl.citation_verification;
  const rag = sl.rag_quality;
  const hand = rag?.heldout?.judge_vs_hand_check;
  return (
    <div>
      <p>
        Measured on {s.date} with <code>{s.model}</code> (answers and citation checks) and <code>{s.embedding_model}</code>{" "}
        (retrieval), over {s.corpus.chunks_on_disk} corpus passages. Each slice is reported on the <strong>original</strong>{" "}
        labelled set (used while building, so optimistic) and on a <strong>held-out</strong> set written before any Phase H run
        and never used for tuning. The held-out set was written by the developer after seeing the corpus, so it is unseen, not blind.
        The hand check of answer sentences was labelled by the developer agent after the run, not by an independent person.
      </p>
      {hand && hand.status === "done" && (
        <p className="notice">
          <strong>What &ldquo;supported&rdquo; means.</strong> In real answers the citation checker accepted{" "}
          {Math.round((hand.false_support_rate ?? 0) * (hand.negatives ?? 0))} of {hand.negatives} sentences that the hand
          check found unsupported. A sentence marked &ldquo;Supported&rdquo; on the Ask screen has been judged supported by the
          language model, not verified by a person. Read the cited passage before relying on it.
        </p>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Slice</th><th>Metric</th><th>Original</th><th>Held-out</th></tr>
          </thead>
          <tbody>
            <Row name="Arithmetic golden set" metric="Engine figures equal to hand-computed, cited values (P1–P10)"
              original={`${sl.arithmetic.matched}/${sl.arithmetic.figures} figures`} heldout="–" />
            <Row name="Tax-year retrieval" metric="Right passage in the top 5 (hit@5), tax-year filter on"
              original={`${pct(r.original?.overall["hit@5"])} of ${r.original?.n}`} heldout={`${pct(r.heldout?.overall["hit@5"])} of ${r.heldout?.n}`} />
            <Row name="Wrong-Act passages" metric="Passages returned from the Act not in force for the year"
              original={String(r.original?.wrong_act_returned.length ?? "–")} heldout={String(r.heldout?.wrong_act_returned.length ?? "–")} />
            {t && <Row name="Temporal traps" metric="Old/new section number asked for the other year: right Act in top 3; answers cite only that Act"
              original={`${pct(t.original?.["retrieval_hit@3"])} · answers ${frac(t.original?.answers)}`}
              heldout={`${pct(t.heldout?.["retrieval_hit@3"])} · answers ${frac(t.heldout?.answers)}`} />}
            {sl.false_premise && <Row name="False premise" metric="Wrong assumption in the question is pointed out"
              original={frac(sl.false_premise.original)} heldout={frac(sl.false_premise.heldout)} />}
            {sl.wrong_jurisdiction && <Row name="Wrong jurisdiction" metric="UK, other treaties or US state/city law: declined or flagged"
              original="not tested" heldout={frac(sl.wrong_jurisdiction.heldout)} />}
            {sl.out_of_scope && <Row name="Out of scope" metric="Non-tax or other-tax questions declined"
              original={frac(sl.out_of_scope.original)} heldout={frac(sl.out_of_scope.heldout)} />}
            {sl.contested_interpretation && <Row name="Contested interpretation" metric="'Interpretation uncertain' notice with both readings"
              original={frac(sl.contested_interpretation.original)} heldout={frac(sl.contested_interpretation.heldout)} />}
            {cv && <Row name="Citation verification" metric="Stage 2 checker agrees with hand labels on claim–passage pairs"
              original={`${pct(cv.original?.accuracy)} of ${cv.original?.n}`} heldout={`${pct(cv.heldout?.accuracy)} of ${cv.heldout?.n}`} />}
            {cv && <Row name="False support on claim pairs" metric="Wrong labelled claims the checker accepted (the error that matters most)"
              original={pct(cv.original?.false_support_rate)} heldout={pct(cv.heldout?.false_support_rate)} />}
            {cv && <Row name="Unchecked citations shown" metric="Answer citations that failed the stage 1 existence/version check"
              original={String(cv.original?.stage1_violations.length)} heldout={String(cv.heldout?.stage1_violations.length)} />}
            {rag && <Row name="Faithfulness" metric="Answer sentences the checker rates fully supported"
              original={`${pct(rag.original?.faithfulness.rate)} of ${rag.original?.faithfulness.sentences}`}
              heldout={`${pct(rag.heldout?.faithfulness.rate)} of ${rag.heldout?.faithfulness.sentences}`} />}
            {rag && <Row name="Answer relevance" metric="Expected key facts present in the answer"
              original="–" heldout={`${pct(rag.heldout?.key_fact_relevance)} (${rag.heldout?.key_fact_cases} cases)`} />}
            {rag && <Row name="Context recall" metric="An expected passage was given to the model"
              original="–" heldout={`${pct(rag.heldout?.context_recall)} (${rag.heldout?.context_recall_cases} cases)`} />}
            {hand && <Row name="Checker vs hand check" metric="Agreement on sentences from held-out answers, labelled by hand"
              original="–" heldout={hand.status === "done" ? `${pct(hand.agreement)} of ${hand.n}` : "pending"} />}
            {hand && hand.status === "done" && <Row name="False support on real answers"
              metric="Sentences labelled unsupported by hand that the checker accepted"
              original="–" heldout={`${Math.round((hand.false_support_rate ?? 0) * (hand.negatives ?? 0))} of ${hand.negatives} (${pct(hand.false_support_rate)})`} />}
          </tbody>
        </table>
      </div>

      <h2>Arithmetic golden set by persona</h2>
      <p className="small muted">{sl.arithmetic.note}</p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Persona</th><th>Description</th><th>Figures matched</th></tr></thead>
          <tbody>
            {sl.arithmetic.by_persona.map((p) => (
              <tr key={p.id}><th scope="row">{p.id}</th><td className="small">{p.title}</td><td>{p.matched}/{p.figures}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Known failures</h2>
      <p className="small">Every case that failed, every retrieval miss and every checker error, as recorded. The causes are discussed in <code>eval/REPORT.md</code>.</p>
      {s.known_failures && s.known_failures.length > 0 ? (
        <ul className="small">
          {s.known_failures.map((f, i) => (
            <li key={i}>
              <span className="badge">{f.set}</span> <strong>{f.id}</strong> · {f.kind}
              {f.slice ? ` (${f.slice})` : ""}: {f.problems?.join("; ") ?? f.q ?? `labelled ${f.label}, checker said ${f.verdict}`}
            </li>
          ))}
        </ul>
      ) : <p className="muted">None recorded.</p>}

      <p className="small muted">
        Run {s.git_commit} · held-out set frozen {s.heldout.frozen_at} · {s.requests.sent} model requests sent by the last run
        ({s.requests.cache_hits} answered from the cache).
      </p>
    </div>
  );
}

export default function EvaluationPage() {
  const [s, setS] = useState<Summary | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    fetch("/api/evaluation")
      .then(async (resp) => {
        const body = await resp.json().catch(() => null);
        if (!resp.ok) throw new Error(body?.detail ?? `HTTP ${resp.status}`);
        setS(body as Summary);
      })
      .catch((e: Error) => setErr(e.message));
  }, []);
  return (
    <div>
      <h1>Evaluation</h1>
      <p className="muted">Where CiteTax fails, not only where it works (SRS/SDS 3.8, NFR-3 and NFR-4).</p>
      {err && <div className="error">Could not load the evaluation results: {err}</div>}
      {!s && !err && <p className="muted">Loading…</p>}
      {s && <Results s={s} />}
    </div>
  );
}
