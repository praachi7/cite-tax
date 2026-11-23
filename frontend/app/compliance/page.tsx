"use client";

import { Cites } from "@/components/Cites";
import { RunGate } from "@/components/RunGate";
import { SourcesPanel } from "@/components/SourcesPanel";
import { formatInr } from "@/lib/format";
import type { Json, StoredRun } from "@/lib/types";

type Status = "ok" | "action" | "unknown" | "na";
const STATUS_TEXT: Record<Status, string> = { ok: "In order", action: "Action needed", unknown: "Not checked", na: "Not required" };

function StatusBadge({ s, text }: { s: Status; text?: string }) {
  return <span className={`badge status-${s}`}>{text ?? STATUS_TEXT[s]}</span>;
}

const BAR_TEXT: Record<string, string> = {
  foreign_source_income: "income from a source outside India",
  foreign_assets: "foreign assets held (Schedule FA)",
  foreign_tax_relief_claimed: "foreign tax relief claimed",
};

function Compliance({ run }: { run: StoredRun }) {
  const e = run.result.estimate;
  const c = e.compliance;
  const codes = new Set(e.flags.map((f) => f.code));
  const flagsBy = (prefix: string) => e.flags.filter((f) => f.code.startsWith(prefix));
  const step = (id: string) => e.trace.find((t) => t.rule_id === id)?.citations ?? [];

  const engagements = (Array.isArray(run.request.profile.engagements) ? run.request.profile.engagements : []) as Record<string, Json>[];
  const usClients = engagements.filter((g) => g.client_is_us_person !== false);
  const w8Flags = flagsBy("W8BEN");
  // No engagements entered says nothing about whether a client is a US person, so that is "not checked".
  const w8Status: Status = w8Flags.length ? "action" : engagements.length === 0 ? "unknown" : usClients.length === 0 ? "na" : "ok";

  const faBar = c.itr4_bars.find((b) => b.bar === "foreign_assets");
  const faFlags = e.flags.filter((f) => f.code === "FOREIGN_ACCOUNT_HELD");
  const faStatus: Status = faBar || faFlags.length ? "action" : "na";

  const lut = run.request.profile.lut_current;
  const lutFlags = flagsBy("GST_LUT");
  const lutStatus: Status = lutFlags.length ? "action" : lut === true ? "ok" : "unknown";

  const ftc = c.ftc_readiness;
  const ftcStatus: Status = !ftc || !ftc.applicable ? "na" : ftc.ready ? "ok" : "action";

  const cites = [
    ...step("ENG.10.itr_form"), ...step("ENG.10.return_due_date"), ...step("ENG.10.advance_tax"),
    ...c.deadlines.flatMap((d) => d.citations), ...(ftc?.items.flatMap((i) => i.citations) ?? []),
    ...[...w8Flags, ...faFlags, ...lutFlags].flatMap((f) => f.citations),
  ];

  return (
    <div>
      <h1>Compliance checklist</h1>

      <div className="panel table-wrap">
        <table className="checklist">
          <thead><tr><th>Item</th><th>Status</th><th>What applies</th><th>Citations</th></tr></thead>
          <tbody>
            <tr>
              <td><strong>Return form</strong></td>
              <td><StatusBadge s="ok" text={c.itr_form} /></td>
              <td>
                {c.itr_form_reasons.length > 0 && <>Because: {c.itr_form_reasons.map((r) => BAR_TEXT[r] ?? r.replaceAll("_", " ")).join("; ")}. </>}
                {c.itr4_bars.length > 0 && (
                  <div className="muted small">
                    ITR-4 barred by: {c.itr4_bars.map((b) => `${BAR_TEXT[b.bar] ?? b.bar} (${b.source})`).join(", ")}
                  </div>
                )}
                {c.depends_on_contested.length > 0 && (
                  <div className="flag warning small">
                    Rests on contested assumption(s) {c.depends_on_contested.join(", ")}.
                    {c.itr4_possible_under_other_reading && " Under the other reading, ITR-4 would apply."} See the notices below.
                  </div>
                )}
              </td>
              <td><Cites list={step("ENG.10.itr_form")} /></td>
            </tr>
            <tr>
              <td><strong>Return due</strong></td>
              <td><StatusBadge s="ok" text={c.return_due_date} /></td>
              <td>{c.return_due_basis === "audit_case" ? "Audit case: accounts must be audited first." : "Non-audit case."}
                {c.regime_filing && <div className="muted small">Regime change filed with: {c.regime_filing.replaceAll("_", " ")}</div>}
              </td>
              <td><Cites list={step("ENG.10.return_due_date")} /></td>
            </tr>
            <tr>
              <td><strong>Advance tax</strong></td>
              <td><StatusBadge s={c.advance_tax.required ? "action" : "na"} text={c.advance_tax.required ? "Required" : "Not required"} /></td>
              <td>
                Net tax {formatInr(c.advance_tax.net_tax_inr)}; schedule: {c.advance_tax.schedule.replaceAll("_", " ")}.
                {c.advance_tax.instalments.length > 0 && (
                  <div className="muted small">{c.advance_tax.instalments.map((i) => `${i.due}: ${i.cumulative_percent}% (${formatInr(i.cumulative_amount_inr)})`).join(" · ")}</div>
                )}
              </td>
              <td><Cites list={step("ENG.10.advance_tax")} /></td>
            </tr>
            <tr>
              <td><strong>{ftc?.form ?? "Form 44 / 67"}</strong> (foreign tax credit)</td>
              <td><StatusBadge s={ftcStatus} text={ftcStatus === "ok" ? "Ready" : ftcStatus === "action" ? "Not ready" : undefined} /></td>
              <td>{ftc?.applicable ? <>Statement under {ftc.rule}, due {ftc.statement_due ?? "—"}. Items below.</> : "No foreign tax credit is claimed."}</td>
              <td>—</td>
            </tr>
            <tr>
              <td><strong>W-8BEN</strong></td>
              <td><StatusBadge s={w8Status} /></td>
              <td>
                {engagements.length === 0
                  ? "No clients entered on the upload screen, so W-8BEN was not checked. Add each client (with its W-8BEN date) to check it."
                  : usClients.length === 0 ? "No client is a US person." : `${usClients.length} US client(s).`}
                {w8Flags.map((f) => <div key={f.code} className="small">{f.message}</div>)}
              </td>
              <td><Cites list={w8Flags.flatMap((f) => f.citations)} /></td>
            </tr>
            <tr>
              <td><strong>Schedule FA</strong> (foreign assets)</td>
              <td><StatusBadge s={faStatus} text={faStatus === "action" ? "Report" : undefined} /></td>
              <td>
                {faStatus === "na" ? "No foreign asset in the profile." : "Foreign assets must be reported in Schedule FA."}
                {faBar && <span className="muted small"> (rests on {faBar.source})</span>}
                {faFlags.map((f) => <div key={f.code} className="small">{f.message}</div>)}
              </td>
              <td><Cites list={faFlags.flatMap((f) => f.citations)} /></td>
            </tr>
            <tr>
              <td><strong>GST / LUT</strong></td>
              <td><StatusBadge s={lutStatus} /></td>
              <td>
                {lut === true ? "A Letter of Undertaking is in force." : lut === false ? "No Letter of Undertaking in force." : "LUT status not given, so it was not checked."}
                {lutFlags.map((f) => <div key={f.code} className="small">{f.message}</div>)}
              </td>
              <td><Cites list={lutFlags.flatMap((f) => f.citations)} /></td>
            </tr>
            {codes.has("FIRA_MISSING") && (
              <tr>
                <td><strong>FIRA / purpose codes</strong></td>
                <td><StatusBadge s="action" /></td>
                <td>{e.flags.find((f) => f.code === "FIRA_MISSING")?.message}</td>
                <td>{e.flags.find((f) => f.code === "FIRA_MISSING")?.source_note ?? "—"}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {ftc?.applicable && (
        <section>
          <h2>{ftc.form} readiness</h2>
          <div className="panel table-wrap">
            <table>
              <thead><tr><th>Item</th><th>Status</th><th>Note</th><th>Citations</th></tr></thead>
              <tbody>
                {ftc.items.map((i) => (
                  <tr key={i.key}>
                    <td>{i.title}</td>
                    <td><span className={`badge readiness-${i.status}`}>{i.status.replaceAll("_", " ")}</span></td>
                    <td>{i.note ?? "—"}</td>
                    <td><Cites list={i.citations} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section>
        <h2>Deadlines</h2>
        <div className="panel table-wrap">
          <table>
            <thead><tr><th>Due</th><th>What</th><th>Status</th><th>Amount</th><th>Citations</th></tr></thead>
            <tbody>
              {c.deadlines.length === 0 && <tr><td colSpan={5} className="muted">No deadlines.</td></tr>}
              {[...c.deadlines].sort((a, b) => a.due.localeCompare(b.due)).map((d) => (
                <tr key={d.key}>
                  <td className="value">{d.due}</td>
                  <td>{d.title}</td>
                  <td>
                    <span className={`badge deadline-${d.status}`}>{d.status.replaceAll("_", " ")}</span>
                    {d.days_left !== null && <div className="muted small">{d.days_left >= 0 ? `${d.days_left} days left` : `${-d.days_left} days ago`}</div>}
                  </td>
                  <td className="value">{d.amount_inr ? formatInr(d.amount_inr) : "—"}</td>
                  <td>{d.citations.length ? <Cites list={d.citations} /> : <span className="muted small">{d.source_note ?? "—"}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!run.request.profile.as_of && <p className="muted small">No &ldquo;measure from&rdquo; date was given, so deadlines are shown as scheduled.</p>}
      </section>

      <SourcesPanel ids={cites} notices={run.result.notices} />
    </div>
  );
}

export default function CompliancePage() {
  return <RunGate>{(run) => <Compliance run={run} />}</RunGate>;
}
