"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { loadEstimate } from "@/lib/api";
import { formatInr, formatValue } from "@/lib/format";
import type { Figure, StoredEstimate } from "@/lib/types";

function Cites({ list }: { list: string[] }) {
  if (!list.length) return <span className="muted">—</span>;
  return (
    <span className="cites">
      {list.map((c) => <span className="cite" key={c}>{c}</span>)}
    </span>
  );
}

function groupBySection(figures: Figure[]): [string, Figure[]][] {
  const out = new Map<string, Figure[]>();
  for (const f of figures) out.set(f.section, [...(out.get(f.section) ?? []), f]);
  return [...out.entries()];
}

// sessionStorage is read on the client only; the server render shows the loading state.
let cached: { raw: string | null; value: StoredEstimate | null } = { raw: null, value: null };
function readStore(): StoredEstimate | null {
  const value = loadEstimate();
  const raw = value ? JSON.stringify(value) : null;
  if (raw !== cached.raw) cached = { raw, value };
  return cached.value;
}
const noSubscribe = () => () => {};

export default function SummaryPage() {
  const stored = useSyncExternalStore(noSubscribe, readStore, () => undefined);

  if (stored === undefined) return <p className="muted">Loading…</p>;
  if (stored === null) {
    return (
      <div className="panel">
        <p>No estimate to show yet.</p>
        <Link href="/">Go to the input screen</Link>
      </div>
    );
  }

  const r = stored.result;
  const adv = r.compliance.advance_tax;

  return (
    <div>
      <h1>Tax summary</h1>
      <div className="panel">
        <p style={{ margin: 0 }}><strong>{stored.label}</strong></p>
        <p style={{ margin: "4px 0 0" }}>
          Governing law: <strong>{r.act.label}</strong> ({r.act.act_id}), parameters from <code>{r.act.param_version}</code>
        </p>
        <div className="actions"><Link href="/">← Change input</Link></div>
      </div>

      {r.flags.length > 0 && (
        <section>
          <h2>Flags</h2>
          {r.flags.map((f) => (
            <div key={f.code + f.rule_id} className={`flag ${f.severity}`}>
              <div><span className="badge">{f.severity}</span> <strong>{f.code}</strong> · <code>{f.rule_id}</code></div>
              <div>{f.message}</div>
              <Cites list={f.citations} />
            </div>
          ))}
        </section>
      )}

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

      {r.compliance.depends_on_contested.length > 0 && (
        <p className="flag warning">
          The ITR form choice rests on contested assumption(s) {r.compliance.depends_on_contested.join(", ")}.
          {r.compliance.itr4_possible_under_other_reading && " Under the other reading, ITR-4 would apply."}
        </p>
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
    </div>
  );
}
