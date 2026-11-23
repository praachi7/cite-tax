"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { estimate, getPersonas, saveEstimate } from "@/lib/api";
import type { ConfigOverrides, Json, Persona } from "@/lib/types";

interface EngagementForm {
  label: string;
  country_of_performance: string;
  amount_inr: string;
  amount_usd: string;
  client_is_us_person: boolean;
  w8ben_on_file: boolean;
  us_tax_withheld_inr: string;
}

interface FormState {
  tax_year: string;
  entity_type: string;
  residential_status: string;
  profession: string;
  electronic: string;
  cash: string;
  non_account_payee_cheque: string;
  declared_profit: string;
  regime_choice: string;
  us_days: [string, string, string]; // calendar years Y, Y-1, Y-2
  us_fixed_base: boolean;
  foreign_clients: boolean;
  foreign_assets_held: boolean;
  platform_wallet_balance_abroad: boolean;
  engagements: EngagementForm[];
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
  electronic: "",
  cash: "",
  non_account_payee_cheque: "",
  declared_profit: "",
  regime_choice: "new",
  us_days: ["", "", ""],
  us_fixed_base: false,
  foreign_clients: true,
  foreign_assets_held: false,
  platform_wallet_balance_abroad: false,
  engagements: [],
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
  us_tax_withheld_inr: "",
};

// Keys the form edits. Anything else in a persona's input (e.g. election_history) is carried through unchanged.
const FORM_KEYS = [
  "persona_id", "tax_year", "entity_type", "residential_status", "profession", "receipts", "declared_profit",
  "regime_choice", "us_days_by_year", "us_fixed_base", "foreign_clients", "foreign_assets_held",
  "platform_wallet_balance_abroad", "engagements",
];

const str = (v: Json | undefined): string => (v === null || v === undefined ? "" : String(v));
const bool = (v: Json | undefined, dflt: boolean): boolean => (typeof v === "boolean" ? v : dflt);

function usYear(f: FormState, carried: Record<string, Json>): number {
  const y = carried.us_calendar_year;
  return typeof y === "number" ? y : Number(f.tax_year);
}

function fromPersona(p: Persona): FormState {
  const i = p.input;
  const r = (i.receipts ?? {}) as Record<string, Json>;
  const days = (i.us_days_by_year ?? {}) as Record<string, Json>;
  const year = typeof i.us_calendar_year === "number" ? i.us_calendar_year : Number(i.tax_year);
  const engs = (Array.isArray(i.engagements) ? i.engagements : []) as Record<string, Json>[];
  return {
    ...EMPTY,
    tax_year: str(i.tax_year),
    entity_type: str(i.entity_type) || EMPTY.entity_type,
    residential_status: str(i.residential_status) || EMPTY.residential_status,
    profession: str(i.profession) || EMPTY.profession,
    electronic: str(r.electronic),
    cash: str(r.cash),
    non_account_payee_cheque: str(r.non_account_payee_cheque),
    declared_profit: str(i.declared_profit),
    regime_choice: str(i.regime_choice) || "new",
    us_days: [str(days[year]), str(days[year - 1]), str(days[year - 2])],
    us_fixed_base: bool(i.us_fixed_base, false),
    foreign_clients: bool(i.foreign_clients, true),
    foreign_assets_held: bool(i.foreign_assets_held, false),
    platform_wallet_balance_abroad: bool(i.platform_wallet_balance_abroad, false),
    engagements: engs.map((e) => ({
      label: str(e.label),
      country_of_performance: str(e.country_of_performance) || "IN",
      amount_inr: str(e.amount_inr),
      amount_usd: str(e.amount_usd),
      client_is_us_person: bool(e.client_is_us_person, true),
      w8ben_on_file: bool(e.w8ben_on_file, true),
      us_tax_withheld_inr: str(e.us_tax_withheld_inr),
    })),
  };
}

function carriedFrom(p: Persona | undefined): Record<string, Json> {
  if (!p) return {};
  return Object.fromEntries(Object.entries(p.input).filter(([k]) => !FORM_KEYS.includes(k)));
}

function toInput(f: FormState, carried: Record<string, Json>, personaId: string): Record<string, Json> {
  const money = (s: string) => (s.trim() === "" ? "0" : s.trim());
  const year = usYear(f, carried);
  const days: Record<string, Json> = {};
  f.us_days.forEach((d, k) => {
    if (d.trim() !== "") days[String(year - k)] = Number(d);
  });
  const input: Record<string, Json> = {
    ...carried,
    persona_id: personaId,
    tax_year: Number(f.tax_year),
    entity_type: f.entity_type,
    residential_status: f.residential_status,
    profession: f.profession,
    receipts: {
      electronic: money(f.electronic),
      cash: money(f.cash),
      non_account_payee_cheque: money(f.non_account_payee_cheque),
    },
    regime_choice: f.regime_choice,
    us_days_by_year: days,
    us_fixed_base: f.us_fixed_base,
    foreign_clients: f.foreign_clients,
    foreign_assets_held: f.foreign_assets_held,
    platform_wallet_balance_abroad: f.platform_wallet_balance_abroad,
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
      return out;
    }),
  };
  if (f.declared_profit.trim() !== "") input.declared_profit = f.declared_profit.trim();
  return input;
}

function toConfig(f: FormState): ConfigOverrides {
  const c: ConfigOverrides = {};
  if (f.a3) c.it_specified_profession_1961 = f.a3 === "true";
  if (f.a5) c.ftc_cap_basis = f.a5;
  if (f.a12) c.platform_wallet_is_foreign_asset = f.a12 === "true";
  if (f.a16) c.itr4_foreign_client_income_is_indian_source = f.a16 === "true";
  return c;
}

export default function InputPage() {
  const router = useRouter();
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [personaId, setPersonaId] = useState("");
  const [form, setForm] = useState<FormState>(EMPTY);
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
    setError(null);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await estimate(toInput(form, carried, personaId || "manual"), toConfig(form));
      saveEstimate({ label: persona ? `${persona.id}: ${persona.title}` : "Manual input", result });
      router.push("/summary");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <h1>Tax estimate input</h1>

      <section className="panel">
        <label>
          Start from a test persona, or enter values by hand
          <select value={personaId} onChange={(e) => pickPersona(e.target.value)}>
            <option value="">Manual input</option>
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
        </div>
      </section>

      <section className="panel">
        <h2>Receipts and profit (rupees)</h2>
        <div className="grid">
          <label>Electronic receipts
            <input inputMode="decimal" value={form.electronic} onChange={(e) => set("electronic", e.target.value)} />
          </label>
          <label>Cash receipts
            <input inputMode="decimal" value={form.cash} onChange={(e) => set("cash", e.target.value)} />
          </label>
          <label>Non-account-payee cheques
            <input inputMode="decimal" value={form.non_account_payee_cheque} onChange={(e) => set("non_account_payee_cheque", e.target.value)} />
          </label>
          <label>Declared profit (blank = presumptive 50%)
            <input inputMode="decimal" value={form.declared_profit} onChange={(e) => set("declared_profit", e.target.value)} />
          </label>
        </div>
      </section>

      <section className="panel">
        <h2>US presence and assets</h2>
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
          <label className="check"><input type="checkbox" checked={form.foreign_assets_held} onChange={(e) => set("foreign_assets_held", e.target.checked)} />Holds foreign assets</label>
          <label className="check"><input type="checkbox" checked={form.platform_wallet_balance_abroad} onChange={(e) => set("platform_wallet_balance_abroad", e.target.checked)} />Platform wallet balance held abroad</label>
        </div>
      </section>

      <section className="panel">
        <h2>Engagements</h2>
        <p className="muted">Where the work was done, client by client. Leave empty if all work was done in India.</p>
        {form.engagements.map((eng, idx) => (
          <div className="engagement" key={idx}>
            <div className="grid">
              <label>Label<input value={eng.label} onChange={(e) => setEng(idx, { label: e.target.value })} /></label>
              <label>Country where performed (ISO)<input value={eng.country_of_performance} onChange={(e) => setEng(idx, { country_of_performance: e.target.value })} /></label>
              <label>Amount (rupees)<input inputMode="decimal" value={eng.amount_inr} onChange={(e) => setEng(idx, { amount_inr: e.target.value })} /></label>
              <label>Amount (USD, optional)<input inputMode="decimal" value={eng.amount_usd} onChange={(e) => setEng(idx, { amount_usd: e.target.value })} /></label>
              <label>US tax withheld (rupees)<input inputMode="decimal" value={eng.us_tax_withheld_inr} onChange={(e) => setEng(idx, { us_tax_withheld_inr: e.target.value })} /></label>
              <label className="check"><input type="checkbox" checked={eng.client_is_us_person} onChange={(e) => setEng(idx, { client_is_us_person: e.target.checked })} />Client is a US person</label>
              <label className="check"><input type="checkbox" checked={eng.w8ben_on_file} onChange={(e) => setEng(idx, { w8ben_on_file: e.target.checked })} />W-8BEN on file</label>
            </div>
            <div className="actions">
              <button type="button" className="secondary" onClick={() => set("engagements", form.engagements.filter((_, k) => k !== idx))}>Remove</button>
            </div>
          </div>
        ))}
        <div className="actions">
          <button type="button" className="secondary" onClick={() => set("engagements", [...form.engagements, { ...NEW_ENGAGEMENT }])}>Add engagement</button>
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
        <button type="submit" disabled={busy}>{busy ? "Computing…" : "Compute tax summary"}</button>
      </div>
    </form>
  );
}
