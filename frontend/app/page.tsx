"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getPersonaCsv, getPersonas, saveRun, uploadEstimate } from "@/lib/api";
import type { ConfigOverrides, Json, Persona, UploadRequest } from "@/lib/types";

interface EngagementForm {
  label: string;
  country_of_performance: string;
  amount_inr: string;
  amount_usd: string;
  client_is_us_person: boolean;
  w8ben_on_file: boolean;
  w8ben_signed: string;
  us_tax_withheld_inr: string;
}

interface FormState {
  tax_year: string;
  entity_type: string;
  residential_status: string;
  profession: string;
  declared_profit: string;
  regime_choice: string;
  us_days: [string, string, string]; // calendar years Y, Y-1, Y-2
  us_fixed_base: boolean;
  foreign_clients: boolean;
  foreign_assets_held: boolean;
  platform_wallet_balance_abroad: boolean;
  engagements: EngagementForm[];
  as_of: string;
  advance_tax_paid_inr: string;
  return_filed: boolean;
  lut_current: string; // "" unknown | "true" | "false"
  unknown_mode_as: "cash" | "other";
  a3: string;
  a5: string;
  a12: string;
  a16: string;
}

const EMPTY: FormState = {
  tax_year: "2026",
  entity_type: "individual",
  residential_status: "resident",
  profession: "information_technology",
  declared_profit: "",
  regime_choice: "new",
  us_days: ["", "", ""],
  us_fixed_base: false,
  foreign_clients: true,
  foreign_assets_held: false,
  platform_wallet_balance_abroad: false,
  engagements: [],
  as_of: "",
  advance_tax_paid_inr: "",
  return_filed: false,
  lut_current: "",
  unknown_mode_as: "cash",
  a3: "",
  a5: "",
  a12: "",
  a16: "",
};

const NEW_ENGAGEMENT: EngagementForm = {
  label: "",
  country_of_performance: "IN",
  amount_inr: "",
  amount_usd: "",
  client_is_us_person: true,
  w8ben_on_file: true,
  w8ben_signed: "",
  us_tax_withheld_inr: "",
};

// Supplied by the CSV, never by the profile (the API rejects them).
const CSV_FIELDS = ["receipts", "remittances", "expense_classifications"];

// Keys the form edits. Anything else in a persona's input (election_history, ftc_documents ...) is carried unchanged.
const FORM_KEYS = [
  "persona_id", "tax_year", "entity_type", "residential_status", "profession", "declared_profit",
  "regime_choice", "us_days_by_year", "us_fixed_base", "foreign_clients", "foreign_assets_held",
  "platform_wallet_balance_abroad", "engagements", "as_of", "advance_tax_paid_inr", "return_filed", "lut_current",
  ...CSV_FIELDS,
];

const str = (v: Json | undefined): string => (v === null || v === undefined ? "" : String(v));
const bool = (v: Json | undefined, dflt: boolean): boolean => (typeof v === "boolean" ? v : dflt);

function usYear(f: FormState, carried: Record<string, Json>): number {
  const y = carried.us_calendar_year;
  return typeof y === "number" ? y : Number(f.tax_year);
}

function fromPersona(p: Persona): FormState {
  const i = p.input;
  const days = (i.us_days_by_year ?? {}) as Record<string, Json>;
  const year = typeof i.us_calendar_year === "number" ? i.us_calendar_year : Number(i.tax_year);
  const engs = (Array.isArray(i.engagements) ? i.engagements : []) as Record<string, Json>[];
  return {
    ...EMPTY,
    tax_year: str(i.tax_year),
    entity_type: str(i.entity_type) || EMPTY.entity_type,
    residential_status: str(i.residential_status) || EMPTY.residential_status,
    profession: str(i.profession) || EMPTY.profession,
    declared_profit: str(i.declared_profit),
    regime_choice: str(i.regime_choice) || "new",
    us_days: [str(days[year]), str(days[year - 1]), str(days[year - 2])],
    us_fixed_base: bool(i.us_fixed_base, false),
    foreign_clients: bool(i.foreign_clients, true),
    foreign_assets_held: bool(i.foreign_assets_held, false),
    platform_wallet_balance_abroad: bool(i.platform_wallet_balance_abroad, false),
    as_of: str(i.as_of),
    advance_tax_paid_inr: str(i.advance_tax_paid_inr),
    return_filed: bool(i.return_filed, false),
    lut_current: typeof i.lut_current === "boolean" ? String(i.lut_current) : "",
    engagements: engs.map((e) => ({
      label: str(e.label),
      country_of_performance: str(e.country_of_performance) || "IN",
      amount_inr: str(e.amount_inr),
      amount_usd: str(e.amount_usd),
      client_is_us_person: bool(e.client_is_us_person, true),
      w8ben_on_file: bool(e.w8ben_on_file, true),
      w8ben_signed: str(e.w8ben_signed),
      us_tax_withheld_inr: str(e.us_tax_withheld_inr),
    })),
  };
}

function carriedFrom(p: Persona | undefined): Record<string, Json> {
  if (!p) return {};
  return Object.fromEntries(Object.entries(p.input).filter(([k]) => !FORM_KEYS.includes(k)));
}

function toProfile(f: FormState, carried: Record<string, Json>, personaId: string): Record<string, Json> {
  const money = (s: string) => (s.trim() === "" ? "0" : s.trim());
  const year = usYear(f, carried);
  const days: Record<string, Json> = {};
  f.us_days.forEach((d, k) => {
    if (d.trim() !== "") days[String(year - k)] = Number(d);
  });
  const profile: Record<string, Json> = {
    ...carried,
    persona_id: personaId,
    tax_year: Number(f.tax_year),
    entity_type: f.entity_type,
    residential_status: f.residential_status,
    profession: f.profession,
    regime_choice: f.regime_choice,
    us_days_by_year: days,
    us_fixed_base: f.us_fixed_base,
    foreign_clients: f.foreign_clients,
    foreign_assets_held: f.foreign_assets_held,
    platform_wallet_balance_abroad: f.platform_wallet_balance_abroad,
    advance_tax_paid_inr: money(f.advance_tax_paid_inr),
    return_filed: f.return_filed,
    engagements: f.engagements.map((e) => {
      const out: Record<string, Json> = {
        label: e.label,
        country_of_performance: e.country_of_performance.trim().toUpperCase() || "IN",
        amount_inr: money(e.amount_inr),
        client_is_us_person: e.client_is_us_person,
        w8ben_on_file: e.w8ben_on_file,
        us_tax_withheld_inr: money(e.us_tax_withheld_inr),
      };
      if (e.amount_usd.trim() !== "") out.amount_usd = e.amount_usd.trim();
      if (e.w8ben_signed.trim() !== "") out.w8ben_signed = e.w8ben_signed.trim();
      return out;
    }),
  };
  if (f.declared_profit.trim() !== "") profile.declared_profit = f.declared_profit.trim();
  if (f.as_of.trim() !== "") profile.as_of = f.as_of.trim();
  if (f.lut_current !== "") profile.lut_current = f.lut_current === "true";
  return profile;
}

function toConfig(f: FormState): ConfigOverrides {
  const c: ConfigOverrides = {};
  if (f.a3) c.it_specified_profession_1961 = f.a3 === "true";
  if (f.a5) c.ftc_cap_basis = f.a5;
  if (f.a12) c.platform_wallet_is_foreign_asset = f.a12 === "true";
  if (f.a16) c.itr4_foreign_client_income_is_indian_source = f.a16 === "true";
  return c;
}

function csvSummary(text: string): string {
  const rows = Math.max(text.split(/\r?\n/).filter((l) => l.trim() !== "").length - 1, 0);
  return `${rows} data row${rows === 1 ? "" : "s"}`;
}

export default function UploadPage() {
  const router = useRouter();
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [personaId, setPersonaId] = useState("");
  const [form, setForm] = useState<FormState>(EMPTY);
  const [csv, setCsv] = useState<{ name: string; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getPersonas().then(setPersonas).catch((e: Error) => setError(`Could not load personas: ${e.message}`));
  }, []);

  const persona = personas.find((p) => p.id === personaId);
  const carried = carriedFrom(persona);
  const year = usYear(form, carried);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm((f) => ({ ...f, [k]: v }));
  const setEng = (idx: number, patch: Partial<EngagementForm>) =>
    setForm((f) => ({ ...f, engagements: f.engagements.map((e, k) => (k === idx ? { ...e, ...patch } : e)) }));

  function pickPersona(id: string) {
    setPersonaId(id);
    const p = personas.find((x) => x.id === id);
    setForm(p ? fromPersona(p) : EMPTY);
    setCsv(null);
    setError(null);
  }

  async function loadSampleCsv() {
    if (!personaId) return;
    setError(null);
    try {
      setCsv({ name: `${personaId}_transactions.csv (synthetic sample)`, text: await getPersonaCsv(personaId) });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function downloadSampleCsv() {
    if (!personaId) return;
    try {
      const text = await getPersonaCsv(personaId);
      const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${personaId}_transactions.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function onFile(file: File | undefined) {
    if (!file) return;
    setError(null);
    file.text().then((text) => setCsv({ name: file.name, text })).catch(() => setError("Could not read that file."));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!csv) {
      setError("Upload a transactions CSV (or use the persona's sample) first.");
      return;
    }
    setBusy(true);
    setError(null);
    const request: UploadRequest = {
      profile: toProfile(form, carried, personaId || "upload"),
      csv_text: csv.text,
      relabels: {},
      unknown_mode_as: form.unknown_mode_as,
      config: toConfig(form),
    };
    try {
      const result = await uploadEstimate(request);
      saveRun({ label: persona ? `${persona.id}: ${persona.title}` : "Own profile", csv_name: csv.name, request, result });
      router.push("/review");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <h1>Persona and upload</h1>

      <section className="panel">
        <label>
          Start from a test persona, or fill in your own profile
          <select value={personaId} onChange={(e) => pickPersona(e.target.value)}>
            <option value="">Own profile</option>
            {personas.map((p) => (
              <option key={p.id} value={p.id}>{p.id}: {p.title}</option>
            ))}
          </select>
        </label>
        {Object.keys(carried).length > 0 && (
          <p className="muted">
            Also sent from {personaId}, not editable here: {Object.keys(carried).map((k) => <code key={k}>{k}</code>)}
          </p>
        )}
      </section>

      <section className="panel">
        <h2>Transactions</h2>
        <p className="muted">
          One row per transaction. <code>date, amount, direction</code> are required; <code>currency, amount_inr,
          counterparty, counterparty_country, description, receipt_mode, fira_ref, purpose_code</code> are read if present.
          Receipts become gross receipts. Expenses are classified on the next screen and never change presumptive income.
        </p>
        <div className="actions">
          <label className="file">
            Upload CSV
            <input type="file" accept=".csv,text/csv" onChange={(e) => onFile(e.target.files?.[0])} />
          </label>
          <button type="button" className="secondary" disabled={!personaId} onClick={loadSampleCsv}>
            Use {personaId || "the persona"}&apos;s sample CSV
          </button>
          <button type="button" className="secondary" disabled={!personaId} onClick={downloadSampleCsv}>
            Download sample
          </button>
        </div>
        {csv ? (
          <p><strong>Loaded:</strong> {csv.name} · {csvSummary(csv.text)}</p>
        ) : (
          <p className="muted">No CSV loaded yet.</p>
        )}
        <label style={{ maxWidth: 420 }}>
          Receipts whose mode the file does not settle count as
          <select value={form.unknown_mode_as} onChange={(e) => set("unknown_mode_as", e.target.value as FormState["unknown_mode_as"])}>
            <option value="cash">Cash (conservative default)</option>
            <option value="other">Other non-electronic mode</option>
          </select>
        </label>
        <p className="muted small">Invoice PDF upload (SRS/SDS 3.5) is not built yet: the prototype has no PDF ingestion.</p>
      </section>

      <section className="panel">
        <h2>Taxpayer</h2>
        <div className="grid">
          <label>Tax year
            <select value={form.tax_year} onChange={(e) => set("tax_year", e.target.value)}>
              <option value="2025">FY 2025-26 (Income-tax Act 1961)</option>
              <option value="2026">Tax Year 2026-27 (Income-tax Act 2025)</option>
            </select>
          </label>
          <label>Entity
            <select value={form.entity_type} onChange={(e) => set("entity_type", e.target.value)}>
              <option value="individual">Individual</option>
              <option value="non_llp_firm">Partnership firm (not LLP)</option>
              <option value="llp">LLP</option>
              <option value="huf">HUF</option>
              <option value="company">Company</option>
            </select>
          </label>
          <label>Residential status
            <select value={form.residential_status} onChange={(e) => set("residential_status", e.target.value)}>
              <option value="resident">Resident and ordinarily resident</option>
              <option value="rnor">Resident but not ordinarily resident</option>
              <option value="non_resident">Non-resident</option>
            </select>
          </label>
          <label>Profession
            <select value={form.profession} onChange={(e) => set("profession", e.target.value)}>
              <option value="information_technology">Information technology</option>
              <option value="other_specified">Other specified profession</option>
              <option value="not_specified">Not a specified profession</option>
            </select>
          </label>
          <label>Regime chosen
            <select value={form.regime_choice} onChange={(e) => set("regime_choice", e.target.value)}>
              <option value="new">New regime</option>
              <option value="old">Old regime</option>
            </select>
          </label>
          <label>Declared profit, rupees (blank = presumptive 50%)
            <input inputMode="decimal" value={form.declared_profit} onChange={(e) => set("declared_profit", e.target.value)} />
          </label>
        </div>
      </section>

      <section className="panel">
        <h2>US presence and foreign accounts</h2>
        <div className="grid">
          {[0, 1, 2].map((k) => (
            <label key={k}>Days in the US in {year - k}
              <input
                inputMode="numeric"
                value={form.us_days[k]}
                onChange={(e) => {
                  const d = [...form.us_days] as FormState["us_days"];
                  d[k] = e.target.value;
                  set("us_days", d);
                }}
              />
            </label>
          ))}
        </div>
        <div className="grid" style={{ marginTop: 12 }}>
          <label className="check"><input type="checkbox" checked={form.us_fixed_base} onChange={(e) => set("us_fixed_base", e.target.checked)} />Fixed base in the US</label>
          <label className="check"><input type="checkbox" checked={form.foreign_clients} onChange={(e) => set("foreign_clients", e.target.checked)} />Fees from clients outside India</label>
          <label className="check"><input type="checkbox" checked={form.foreign_assets_held} onChange={(e) => set("foreign_assets_held", e.target.checked)} />Holds foreign accounts or assets</label>
          <label className="check"><input type="checkbox" checked={form.platform_wallet_balance_abroad} onChange={(e) => set("platform_wallet_balance_abroad", e.target.checked)} />Platform wallet balance held abroad</label>
        </div>
      </section>

      <section className="panel">
        <h2>Clients and W-8BEN</h2>
        <p className="muted">Where the work was done, client by client. Leave empty if all work was done in India.</p>
        {form.engagements.map((eng, idx) => (
          <div className="engagement" key={idx}>
            <div className="grid">
              <label>Label<input value={eng.label} onChange={(e) => setEng(idx, { label: e.target.value })} /></label>
              <label>Country where performed (ISO)<input value={eng.country_of_performance} onChange={(e) => setEng(idx, { country_of_performance: e.target.value })} /></label>
              <label>Amount (rupees)<input inputMode="decimal" value={eng.amount_inr} onChange={(e) => setEng(idx, { amount_inr: e.target.value })} /></label>
              <label>Amount (USD, optional)<input inputMode="decimal" value={eng.amount_usd} onChange={(e) => setEng(idx, { amount_usd: e.target.value })} /></label>
              <label>US tax withheld (rupees)<input inputMode="decimal" value={eng.us_tax_withheld_inr} onChange={(e) => setEng(idx, { us_tax_withheld_inr: e.target.value })} /></label>
              <label>W-8BEN signed on<input type="date" value={eng.w8ben_signed} onChange={(e) => setEng(idx, { w8ben_signed: e.target.value })} /></label>
              <label className="check"><input type="checkbox" checked={eng.client_is_us_person} onChange={(e) => setEng(idx, { client_is_us_person: e.target.checked })} />Client is a US person</label>
              <label className="check"><input type="checkbox" checked={eng.w8ben_on_file} onChange={(e) => setEng(idx, { w8ben_on_file: e.target.checked })} />W-8BEN on file</label>
            </div>
            <div className="actions">
              <button type="button" className="secondary" onClick={() => set("engagements", form.engagements.filter((_, k) => k !== idx))}>Remove</button>
            </div>
          </div>
        ))}
        <div className="actions">
          <button type="button" className="secondary" onClick={() => set("engagements", [...form.engagements, { ...NEW_ENGAGEMENT }])}>Add client</button>
        </div>
      </section>

      <section className="panel">
        <h2>Compliance status</h2>
        <div className="grid">
          <label>Measure deadlines from (blank = undated)
            <input type="date" value={form.as_of} onChange={(e) => set("as_of", e.target.value)} />
          </label>
          <label>Advance tax already paid (rupees)
            <input inputMode="decimal" value={form.advance_tax_paid_inr} onChange={(e) => set("advance_tax_paid_inr", e.target.value)} />
          </label>
          <label>GST Letter of Undertaking in force
            <select value={form.lut_current} onChange={(e) => set("lut_current", e.target.value)}>
              <option value="">Not known</option><option value="true">Yes</option><option value="false">No</option>
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={form.return_filed} onChange={(e) => set("return_filed", e.target.checked)} />Return already filed</label>
        </div>
      </section>

      <section className="panel">
        <h2>Contested points (assumptions)</h2>
        <p className="muted">Leave on default to use the documented conservative reading from the assumptions register.</p>
        <div className="grid">
          <label>A-3: IT is a specified profession (1961 Act)
            <select value={form.a3} onChange={(e) => set("a3", e.target.value)}>
              <option value="">Default</option><option value="true">Yes</option><option value="false">No</option>
            </select>
          </label>
          <label>A-5: foreign tax credit cap basis
            <select value={form.a5} onChange={(e) => set("a5", e.target.value)}>
              <option value="">Default</option><option value="deemed_income">Deemed income</option><option value="gross_receipts">Gross receipts</option>
            </select>
          </label>
          <label>A-12: platform wallet is a foreign asset
            <select value={form.a12} onChange={(e) => set("a12", e.target.value)}>
              <option value="">Default</option><option value="true">Yes</option><option value="false">No</option>
            </select>
          </label>
          <label>A-16: foreign-client fees are Indian-source (ITR-4)
            <select value={form.a16} onChange={(e) => set("a16", e.target.value)}>
              <option value="">Default</option><option value="true">Yes</option><option value="false">No</option>
            </select>
          </label>
        </div>
      </section>

      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={busy || !csv}>{busy ? "Computing…" : "Classify and estimate"}</button>
      </div>
    </form>
  );
}
