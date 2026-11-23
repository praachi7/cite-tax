"use client";

import Link from "next/link";
import { Cites } from "@/components/Cites";
import { RunGate } from "@/components/RunGate";
import { SourcesPanel } from "@/components/SourcesPanel";
import { formatInr, formatValue } from "@/lib/format";
import type { Figure, StoredRun } from "@/lib/types";

function groupBySection(figures: Figure[]): [string, Figure[]][] {
  const out = new Map<string, Figure[]>();
  for (const f of figures) out.set(f.section, [...(out.get(f.section) ?? []), f]);
  return [...out.entries()];
}

function Summary({ run }: { run: StoredRun }) {
  const r = run.result.estimate;
  const adv = r.compliance.advance_tax;
  // Every citation shown on this screen: figures, assumptions applied and the audit trace.
  const figureCites = [
    ...r.figures.flatMap((f) => f.citations),
    ...r.assumptions_applied.flatMap((a) => a.citations),
    ...r.trace.flatMap((t) => t.citations),
  ];
  const blocking = r.flags.filter((f) => f.severity === "blocker" || f.severity === "high").length;

  return (
    <div>
      <h1>Tax summary</h1>
      <div className="panel">
        <p style={{ margin: 0 }}>
          Governing law: <span className="badge act">{r.act.act_id === "IT2025" ? "Income-tax Act 2025" : "Income-tax Act 1961"}</span>{" "}
          <strong>{r.act.label}</strong>, parameters from <code>{r.act.param_version}</code>
        </p>
        <p style={{ margin: "6px 0 0" }}>
          {r.flags.length} flag{r.flags.length === 1 ? "" : "s"}
          {blocking > 0 && <> ({blocking} high or blocker)</>} · see the <Link href="/audit">audit-risk report</Link> and the{" "}
          <Link href="/compliance">compliance checklist</Link>.
        </p>
      </div>

      {groupBySection(r.figures).map(([section, figs]) => (
        <section key={section}>
          <h2>{section}</h2>
          <div className="panel table-wrap">
            <table>
              <thead>
                <tr><th>Figure</th><th>Value</th><th>Rule ID</th><th>Citations</th></tr>
              </thead>
              <tbody>
                {figs.map((f) => (
                  <tr key={f.path}>
                    <td>{f.label}</td>
                    <td className="value">{formatValue(f.value, f.unit)}</td>
                    <td><code>{f.rule_id}</code></td>
                    <td>
                      {f.citations.length ? <Cites list={f.citations} /> : <span className="muted">Selected by tax year from <code>{f.param_version}</code></span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      {adv.instalments.length > 0 && (
        <section>
          <h2>Advance tax instalments</h2>
          <div className="panel table-wrap">
            <table>
              <thead><tr><th>Due</th><th>Cumulative %</th><th>Cumulative amount</th><th>Rule ID</th></tr></thead>
              <tbody>
                {adv.instalments.map((i) => (
                  <tr key={i.due}>
                    <td>{i.due}</td>
                    <td>{i.cumulative_percent}%</td>
                    <td className="value">{formatInr(i.cumulative_amount_inr)}</td>
                    <td><code>ENG.10.advance_tax</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section>
        <h2>Assumptions applied</h2>
        <div className="panel table-wrap">
          <table>
            <thead><tr><th>ID</th><th>Status</th><th>Setting</th><th>Reading</th><th>Citations</th></tr></thead>
            <tbody>
              {r.assumptions_applied.map((a) => (
                <tr key={a.id}>
                  <td><strong>{a.id}</strong></td>
                  <td>{a.status}</td>
                  <td><code>{a.config_flag} = {String(a.value)}</code> {a.is_default ? <span className="muted">(default)</span> : <span className="badge">override</span>}</td>
                  <td>{a.reading ?? "—"}</td>
                  <td><Cites list={a.citations} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>Full audit trace</h2>
        {r.trace.map((t, k) => (
          <details key={k} className="panel">
            <summary>
              Step {t.step} · <code>{t.rule_id}</code> · {t.title}
            </summary>
            <p className="muted">Parameters: <code>{t.param_version}</code>{t.param_keys.length > 0 && <> · {t.param_keys.join(", ")}</>}</p>
            <Cites list={t.citations} />
            {t.note && <p>{t.note}</p>}
            <pre>{JSON.stringify({ inputs: t.inputs, outputs: t.outputs }, null, 2)}</pre>
          </details>
        ))}
      </section>

      <SourcesPanel ids={figureCites} notices={run.result.notices} />
    </div>
  );
}

export default function SummaryPage() {
  return <RunGate>{(run) => <Summary run={run} />}</RunGate>;
}
