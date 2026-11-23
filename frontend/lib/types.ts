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
  severity: "info" | "low" | "medium" | "high" | "blocker" | string;
  message: string;
  rule_id: string;
  citations: string[];
  assumptions?: string[];       // contested assumption IDs the flag rests on
  source_note?: string | null;  // a secondary source not in the corpus, shown instead of a citation
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

export interface ConfigOverrides {
  it_specified_profession_1961?: boolean;
  ftc_cap_basis?: string;
  platform_wallet_is_foreign_asset?: boolean;
  itr4_foreign_client_income_is_indian_source?: boolean;
}

// ---- Phase G: upload, review, compliance, sources, ask ----

export interface Deadline {
  key: string;
  title: string;
  due: string;
  citations: string[];
  status: "scheduled" | "upcoming" | "due_soon" | "passed" | "done" | string;
  days_left: number | null;
  amount_inr: string | null;
  source_note: string | null;
}

export interface ReadinessItem {
  key: string;
  title: string;
  status: "ready" | "missing" | "pending" | "not_required" | string;
  citations: string[];
  note: string | null;
}

export interface FtcReadiness {
  applicable: boolean;
  form: string;
  rule: string;
  statement_due: string | null;
  items: ReadinessItem[];
  ready: boolean;
}

export interface Compliance {
  itr_form: string;
  itr_form_reasons: string[];
  itr4_bars: { bar: string; source: string }[];
  itr4_possible_under_other_reading: boolean;
  depends_on_contested: string[];
  advance_tax: {
    required: boolean;
    net_tax_inr: string;
    schedule: string;
    instalments: Instalment[];
    shortfall_interest_percent: string | null;
  };
  return_due_date: string;
  return_due_basis: string;
  regime_filing: string | null;
  ftc_readiness: FtcReadiness | null;
  deadlines: Deadline[];
}

export interface Estimate {
  persona_id: string;
  act: { act_id: string; label: string; tax_year: number; param_version: string };
  income: { presumptive_amount: string; income: string | null; basis: string; books_audit_required: boolean; tax_audit_required: boolean };
  receipts_test: { total: string; cash_share_percent: string; applicable_limit: string; within_limit: boolean };
  compliance: Compliance;
  figures: Figure[];
  flags: Flag[];
  trace: TraceStep[];
  assumptions_applied: AssumptionApplied[];
}

export interface Transaction {
  id: string;
  line: number;
  date: string;
  direction: "receipt" | "expense";
  amount: string;
  currency: string;
  amount_inr: string;
  foreign_tax_withheld_inr: string;
  counterparty: string;
  counterparty_country: string;
  description: string;
  receipt_mode: string | null;
  mode_source: string | null;
  mode_reason: string;
  fira_ref: string;
  purpose_code: string;
}

export interface Classification {
  transaction_id: string;
  category: string;
  confidence: string;
  method: string;
  rule_id: string | null;
  reason: string;
  candidates: string[];
}

export interface ClassificationRow extends Classification {
  predicted: Classification;
}

export interface Correction {
  transaction_id: string;
  kind: "corrected" | "confirmed";
  predicted: string;
  predicted_confidence: string;
  corrected_to: string;
}

export interface RowError {
  line: number;
  field: string;
  message: string;
}

export interface ProfitComparison {
  gross_receipts: string;
  presumptive_income: string;
  business_expenses: string;
  uncertain_expenses: string;
  actual_profit_high: string;
  actual_profit_low: string;
  below_presumptive: "yes" | "no" | "depends_on_uncertain";
  note: string;
}

export interface NoticeReading {
  key: string;
  statement: string;
  citations: string[];
  is_default: boolean;
}

export interface Notice {
  assumption_id: string;
  question: string;
  readings: NoticeReading[];
  default_reason: string;
  config_flag: string;
  triggered_by: string[];
  disclaimer: string;
  result_depends_on_it?: boolean;
}

export interface UploadResult {
  estimate: Estimate;
  transactions: Transaction[];
  classifications: ClassificationRow[];
  corrections: Correction[];
  parse_errors: RowError[];
  receipt_warnings: string[];
  unknown_mode_as: string;
  profit_comparison: ProfitComparison;
  notices: Notice[];
  disclaimer: string;
}

export interface UploadRequest {
  profile: Record<string, Json>;
  csv_text: string;
  relabels: Record<string, string>;
  unknown_mode_as: "cash" | "other";
  config: ConfigOverrides;
}

export interface StoredRun {
  label: string;
  csv_name: string;
  request: UploadRequest;
  result: UploadResult;
}

export interface Source {
  id: string;
  label: string;
  resolved: boolean;
  chunk_id?: string;
  source_id?: string;
  breadcrumb?: string;
  heading?: string | null;
  text?: string;
  reviewed?: boolean;
}

export interface AnswerSentence {
  text: string;
  cites: string[];
  chunk_ids: string[];
  stage1_ok: boolean;
  stage1_problems: string[];
  verdict: "supported" | "partially_supported" | "not_supported" | "unsupported_citation" | string;
  reason: string;
}

export interface AskAnswer {
  question: string;
  tax_year: number;
  act_id: string;
  status: "answered" | "partially_verified" | "declined" | string;
  sentences: AnswerSentence[];
  premise_issue: string;
  decline_reason: string;
  notices: Notice[];
  passages: string[];
  retrieval_similarity: number;
  model: string;
  disclaimer: string;
}
