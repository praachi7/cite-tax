"use client";

import Link from "next/link";
import { Cites } from "@/components/Cites";
import { RunGate } from "@/components/RunGate";
import { SourcesPanel } from "@/components/SourcesPanel";
import { formatInr } from "@/lib/format";
import type { Flag, StoredRun } from "@/lib/types";

const ORDER = ["blocker", "high", "medium", "low", "info"];

// What the user still has to produce or check, per flag code. Codes not listed show only the engine's message.
const DOCS_NEEDED: Record<string, string> = {
  TAX_AUDIT_REQUIRED: "Books of account and a tax audit report by an accountant before the return.",
  PROFIT_BELOW_50: "Books of account and a tax audit, because profit is declared below the presumptive 50%.",
  CASH_SHARE_ABOVE_5: "Records of cash and non-account-payee receipts; the lower receipts limit applies.",
  RECEIPTS_NEAR_LIMIT: "Watch receipts for the rest of the year; above the limit the presumptive scheme is lost.",
  US_DAYS_TRIGGER: "Travel records for days in the US; a US return is likely needed.",
  US_DAYS_WARNING: "Travel records for days in the US; stay below the treaty threshold or plan for US tax.",
  US_RETURN_REQUIRED: "A US federal return (Form 1040-NR) for the year.",
  FTC_DOCS_INCOMPLETE: "Foreign TIN, certificate of US tax deducted, treaty article and rate (see the Form 44/67 readiness list).",
  FTC_ACCOUNTANT_VERIFICATION: "Verification by an accountant of the foreign tax statement.",
  W8BEN_INVALID: "A valid, signed Form W-8BEN for each US client.",
  US_FIXED_BASE: "Details of the fixed base in the US; income attributable to it may be taxed there.",
  US_SUBSTANTIAL_PRESENCE: "Travel records; US residence under the substantial presence test needs review.",
  PROFIT_REQUIRED: "A declared profit figure: the presumptive scheme is not available.",
  REGIME_OPT_OUT_BARRED: "Earlier regime elections (Form 10-IEA); no further opt-out is allowed.",
  US_TAX_ON_INDIA_WORK: "Evidence the work was done in India, and a US refund claim (Form 1040-NR).",
  FOREIGN_ACCOUNT_HELD: "Year-end balances and peak values for Schedule FA.",
  FIRA_MISSING: "FIRA / e-FIRA and RBI purpose code from the bank for each inward remittance.",
  GST_LUT_MISSING: "A GST Letter of Undertaking for zero-rated exports, or GST registration review.",
  LOW_CLASSIFICATION_CONFIDENCE: "Review the uncertain expense labels on the classification review screen.",
  ADVANCE_TAX_DUE: "Pay the advance tax instalment before the due date.",
  RETURN_DUE: "File the return before the due date.",
};

function FlagCard({ f }: { f: Flag }) {
  return (
    <div className={`flag ${f.severity}`}>
      <div>
        <span className="badge">{f.severity}</span> <strong>{f.code}</strong> · <code>{f.rule_id}</code>
        {f.assumptions && f.assumptions.length > 0 && <span className="badge warn">rests on {f.assumptions.join(", ")}</span>}
      </div>
      <div>{f.message}</div>
      {DOCS_NEEDED[f.code] && <div className="small"><strong>Still required:</strong> {DOCS_NEEDED[f.code]}</div>}
      {f.code === "LOW_CLASSIFICATION_CONFIDENCE" && <div className="small"><Link href="/review">Go to classification review →</Link></div>}
      {f.citations.length > 0 ? <Cites list={f.citations} /> : <div className="muted small">{f.source_note ?? "Internal rule; no statute cited."}</div>}
    </div>
  );
}

function Audit({ run }: { run: StoredRun }) {
  const e = run.result.estimate;
  const pc = run.result.profit_comparison;
  const flags = [...e.flags].sort((a, b) => ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity));
  const counts = ORDER.map((s) => [s, flags.filter((f) => f.severity === s).length] as const).filter(([, n]) => n > 0);

  return (
    <div>
      <h1>Audit-risk report</h1>
      <div className="panel">
        {flags.length === 0 ? (
          <p style={{ margin: 0 }}>No flags were raised for this run.</p>
        ) : (
          <p style={{ margin: 0 }}>
            {flags.length} flag{flags.length === 1 ? "" : "s"}: {counts.map(([s, n]) => `${n} ${s}`).join(", ")}.
          </p>
        )}
      </div>

      {flags.map((f) => <FlagCard key={f.code + f.rule_id} f={f} />)}

      <section>
        <h2>Actual profit beside the presumptive figure</h2>
        <div className="panel table-wrap">
          <table>
            <tbody>
              <tr><td>Gross receipts</td><td className="value">{formatInr(pc.gross_receipts)}</td></tr>
              <tr><td>Presumptive income (50%)</td><td className="value">{formatInr(pc.presumptive_income)}</td></tr>
              <tr><td>Expenses labelled business</td><td className="value">{formatInr(pc.business_expenses)}</td></tr>
              <tr><td>Expenses labelled uncertain</td><td className="value">{formatInr(pc.uncertain_expenses)}</td></tr>
              <tr><td>Actual profit, if every uncertain expense is personal</td><td className="value">{formatInr(pc.actual_profit_high)}</td></tr>
              <tr><td>Actual profit, if every uncertain expense is business</td><td className="value">{formatInr(pc.actual_profit_low)}</td></tr>
            </tbody>
          </table>
          <p className={pc.below_presumptive === "no" ? "muted" : "flag medium"}>{pc.note}</p>
          <p className="muted small">Informational only: it never feeds the tax computation.</p>
        </div>
      </section>

      <SourcesPanel ids={flags.flatMap((f) => f.citations)} notices={run.result.notices} />
    </div>
  );
}

export default function AuditPage() {
  return <RunGate>{(run) => <Audit run={run} />}</RunGate>;
}
