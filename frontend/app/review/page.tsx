"use client";

import Link from "next/link";
import { useState } from "react";
import { RunGate } from "@/components/RunGate";
import { saveRun, uploadEstimate } from "@/lib/api";
import { CATEGORIES, CATEGORY_LABEL, CONFIDENCE_FLOOR } from "@/lib/categories";
import { formatInr } from "@/lib/format";
import type { ClassificationRow, StoredRun, Transaction } from "@/lib/types";

const needsReview = (c: ClassificationRow) =>
  c.method !== "user" && (c.category === "uncertain" || Number(c.confidence) < CONFIDENCE_FLOOR);

// Two reasons a row is listed, shown differently so the highlight carries meaning:
//   label   - the classifier has no answer (no rule matched, or rules disagree): the user must choose;
//   confirm - it has an answer, but only from a generic keyword (75%, under the 80% review bar).
type ReviewKind = "label" | "confirm";

function reviewKind(c: ClassificationRow): ReviewKind | null {
  if (!needsReview(c)) return null;
  return c.category === "uncertain" ? "label" : "confirm";
}

const pct = (x: string | number) => Math.round(Number(x) * 100);

function reviewWhy(c: ClassificationRow): string {
  const p = c.predicted;
  if (p.category === "uncertain") {
    if (p.candidates.length > 1) {
      const names = p.candidates.map((k) => CATEGORY_LABEL[k] ?? k).join(" vs ");
      return `Rules point to different labels (${names}): choose the right one.`;
    }
    return "No rule recognised this description: choose a label.";
  }
  return `Matched only a generic word, so ${pct(p.confidence)}% is under the ${pct(CONFIDENCE_FLOOR)}% review bar: confirm or change it.`;
}

const KIND_BADGE: Record<ReviewKind, string> = { label: "Needs a label", confirm: "Please confirm" };

function Review({ run }: { run: StoredRun }) {
  const r = run.result;
  const [relabels, setRelabels] = useState<Record<string, string>>(run.request.relabels);
  const [showAll, setShowAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Presumptive income before and after the last completed re-run; set only once the new result is in.
  const [check, setCheck] = useState<{ before: string; after: string } | null>(null);

  const txById = new Map<string, Transaction>(r.transactions.map((t) => [t.id, t]));
  const order = (c: ClassificationRow) => ({ label: 0, confirm: 1 } as Record<string, number>)[reviewKind(c) ?? ""] ?? 2;
  const rows = [...r.classifications].sort((a, b) => order(a) - order(b));
  const flagged = rows.filter(needsReview);
  const toLabel = flagged.filter((c) => reviewKind(c) === "label");
  const toConfirm = flagged.filter((c) => reviewKind(c) === "confirm");
  const unconfirmed = toConfirm.filter((c) => !(c.transaction_id in relabels));
  const visible = showAll ? rows : flagged;
  const pending = Object.entries(relabels).filter(([id, cat]) => run.request.relabels[id] !== cat).length +
    Object.keys(run.request.relabels).filter((id) => !(id in relabels)).length;
  const presumptive = r.estimate.income.presumptive_amount;
  const receipts = r.transactions.filter((t) => t.direction === "receipt");

  function choose(id: string, value: string) {
    setRelabels((cur) => {
      const next = { ...cur };
      if (value === "") delete next[id];
      else next[id] = value;
      return next;
    });
  }

  // Keep the classifier's label for every generic-keyword row not yet touched; the re-run logs them as confirmations.
  function confirmAllKeywordMatches() {
    setRelabels((cur) => {
      const next = { ...cur };
      for (const c of toConfirm) if (!(c.transaction_id in next)) next[c.transaction_id] = c.predicted.category;
      return next;
    });
  }

  async function rerun() {
    setBusy(true);
    setError(null);
    setCheck(null);
    try {
      const request = { ...run.request, relabels };
      const result = await uploadEstimate(request);
      saveRun({ ...run, request, result });
      setCheck({ before: presumptive, after: result.estimate.income.presumptive_amount });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Classification review</h1>

      <div className="panel">
        <p style={{ margin: 0 }}>
          <strong>{r.classifications.length}</strong> expenses classified ·{" "}
          <strong>{toLabel.length}</strong> need a label (the classifier had no answer) ·{" "}
          <strong>{toConfirm.length}</strong> to confirm (generic-word matches) ·{" "}
          <strong>{r.corrections.length}</strong> labelled by you
        </p>
        <p className="muted small" style={{ margin: "6px 0 0" }}>
          Why so many to confirm? This prototype classifies by rules: a named merchant (e.g. GitHub) scores{" "}
          95%, a generic word (e.g. &ldquo;pharmacy&rdquo;) only 75%, and anything under{" "}
          {pct(CONFIDENCE_FLOOR)}% is listed for a quick check. A quick confirm is enough for most of them.
        </p>
        <p className="invariant">
          Presumptive income: <strong>{formatInr(presumptive)}</strong> (50% of gross receipts {formatInr(r.estimate.receipts_test.total)}).
          Expense labels never change it: they feed only the confidence flag and the profit comparison
          (s.44ADA(2) of the 1961 Act; s.58 of the 2025 Act).
          {check !== null && (check.before === check.after
            ? <> <span className="badge ok">unchanged after re-run</span></>
            : <> <span className="badge warn">changed from {formatInr(check.before)}: please report this as a bug</span></>)}
        </p>
      </div>

      {r.parse_errors.length > 0 && (
        <div className="flag medium">
          <strong>{r.parse_errors.length} CSV row(s) were left out:</strong>
          <ul>{r.parse_errors.map((e, k) => <li key={k}>line {e.line}, {e.field}: {e.message}</li>)}</ul>
        </div>
      )}
      {r.receipt_warnings.length > 0 && (
        <div className="flag medium">
          <strong>Receipt modes:</strong>
          <ul>{r.receipt_warnings.map((w, k) => <li key={k}>{w}</li>)}</ul>
        </div>
      )}

      <section>
        <h2>Expenses</h2>
        <div className="actions" style={{ marginTop: 0, marginBottom: 8 }}>
          <label className="check">
            <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
            Show all {rows.length} expenses (otherwise only the {flagged.length} that need review)
          </label>
          {unconfirmed.length > 0 && (
            <button type="button" className="secondary" onClick={confirmAllKeywordMatches}>
              Confirm all {unconfirmed.length} generic-word matches as predicted
            </button>
          )}
        </div>
        <div className="panel table-wrap">
          <table>
            <thead>
              <tr><th>Date</th><th>Description</th><th>Amount</th><th>Predicted</th><th>Confidence</th><th>Why listed</th><th>Your label</th></tr>
            </thead>
            <tbody>
              {visible.length === 0 && (
                <tr><td colSpan={7} className="muted">Nothing needs review. Tick &ldquo;Show all&rdquo; to relabel any expense.</td></tr>
              )}
              {visible.map((c) => {
                const t = txById.get(c.transaction_id);
                const p = c.predicted;
                const weak = p.category === "uncertain" || Number(p.confidence) < CONFIDENCE_FLOOR;
                const kind = reviewKind(c);
                return (
                  <tr key={c.transaction_id} className={kind === "label" ? "row-review" : kind === "confirm" ? "row-confirm" : undefined}>
                    <td>{t?.date}</td>
                    <td>
                      {t?.description}
                      <div className="muted small">{c.transaction_id}{t?.counterparty && <> · {t.counterparty}</>}</div>
                    </td>
                    <td className="value">{formatInr(t?.amount_inr ?? null)}</td>
                    <td>
                      {CATEGORY_LABEL[p.category] ?? p.category}
                      <div className="muted small">{p.reason}{p.candidates.length > 0 && <> ({p.candidates.join(", ")})</>}</div>
                    </td>
                    <td>
                      <span className={weak ? "badge warn" : "badge"}>{Math.round(Number(p.confidence) * 100)}%</span>
                      <div className="muted small">{p.method === "rule" ? `rule ${p.rule_id ?? ""}` : "no rule"}</div>
                    </td>
                    <td>
                      {kind ? (
                        <>
                          <span className={kind === "label" ? "badge warn" : "badge"}>{KIND_BADGE[kind]}</span>
                          <div className="small">{reviewWhy(c)}</div>
                        </>
                      ) : c.method === "user" ? (
                        <span className="muted small">Labelled by you</span>
                      ) : (
                        <span className="muted small">Named-merchant match</span>
                      )}
                    </td>
                    <td>
                      <select
                        aria-label={`Label for ${c.transaction_id}`}
                        value={relabels[c.transaction_id] ?? ""}
                        onChange={(e) => choose(c.transaction_id, e.target.value)}
                      >
                        <option value="">Keep prediction</option>
                        {CATEGORIES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="actions">
          <button type="button" onClick={rerun} disabled={busy}>
            {busy ? "Re-running…" : `Re-run with my labels${pending ? ` (${pending} change${pending === 1 ? "" : "s"})` : ""}`}
          </button>
          <Link href="/summary">Continue to the tax summary →</Link>
        </div>
      </section>

      {r.corrections.length > 0 && (
        <section>
          <h2>Correction log</h2>
          <p className="muted small">Kept with this session&apos;s run; the prototype has no audit database yet.</p>
          <div className="panel table-wrap">
            <table>
              <thead><tr><th>Transaction</th><th>Classifier said</th><th>Confidence</th><th>Your label</th><th>Kind</th></tr></thead>
              <tbody>
                {r.corrections.map((c) => (
                  <tr key={c.transaction_id}>
                    <td><code>{c.transaction_id}</code></td>
                    <td>{CATEGORY_LABEL[c.predicted] ?? c.predicted}</td>
                    <td>{Math.round(Number(c.predicted_confidence) * 100)}%</td>
                    <td>{CATEGORY_LABEL[c.corrected_to] ?? c.corrected_to}</td>
                    <td>{c.kind}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section>
        <h2>Receipts ({receipts.length})</h2>
        <details className="panel">
          <summary>Receipts are not classified; they make up gross receipts by mode.</summary>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Description</th><th>Credited</th><th>Mode</th><th>FIRA</th><th>Purpose</th></tr></thead>
              <tbody>
                {receipts.map((t) => (
                  <tr key={t.id}>
                    <td>{t.date}</td>
                    <td>{t.description}<div className="muted small">{t.id} · {t.counterparty_country || "country not given"}</div></td>
                    <td className="value">{formatInr(t.amount_inr)}</td>
                    <td>{t.receipt_mode}<div className="muted small">{t.mode_source}</div></td>
                    <td>{t.fira_ref || <span className="muted">—</span>}</td>
                    <td>{t.purpose_code || <span className="muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>
    </div>
  );
}

export default function ReviewPage() {
  return <RunGate>{(run) => <Review run={run} />}</RunGate>;
}
