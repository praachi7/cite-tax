// Shapes returned by the CiteTax API (backend/api). Money is a decimal string in rupees.

export type Json = string | number | boolean | null | Json[] | { [k: string]: Json };

export interface Persona {
  id: string;
  title: string;
  input: Record<string, Json>;
}

export interface Figure {
  section: string;
  path: string;
  label: string;
  value: Json;
  unit: "inr" | "percent" | "days" | null;
  rule_id: string;
  citations: string[];
  param_version: string | null;
}

export interface TraceStep {
  step: number;
  rule_id: string;
  title: string;
  param_version: string;
  param_keys: string[];
  citations: string[];
  inputs: Record<string, Json>;
  outputs: Record<string, Json>;
  note: string | null;
}

export interface Flag {
  code: string;
  severity: "info" | "warning" | "blocker" | string;
  message: string;
  rule_id: string;
  citations: string[];
}

export interface AssumptionApplied {
  id: string;
  status: string;
  config_flag: string;
  value: Json;
  reading: string | null;
  is_default: boolean;
  citations: string[];
}

export interface Instalment {
  due: string;
  cumulative_percent: string;
  cumulative_amount_inr: string;
}

export interface EstimateResult {
  persona_id: string;
  act: { act_id: string; label: string; tax_year: number; param_version: string };
  compliance: {
    itr_form: string;
    itr_form_reasons: string[];
    depends_on_contested: string[];
    itr4_possible_under_other_reading: boolean;
    advance_tax: { required: boolean; schedule: string; instalments: Instalment[] };
  };
  figures: Figure[];
  flags: Flag[];
  trace: TraceStep[];
  assumptions_applied: AssumptionApplied[];
  disclaimer: string;
}

export interface ConfigOverrides {
  it_specified_profession_1961?: boolean;
  ftc_cap_basis?: string;
  platform_wallet_is_foreign_asset?: boolean;
  itr4_foreign_client_income_is_indian_source?: boolean;
}

export interface StoredEstimate {
  label: string;
  result: EstimateResult;
}
