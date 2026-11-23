import type { Figure, Json } from "./types";

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

export function formatInr(v: Json): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? `Rs ${inr.format(n)}` : String(v);
}

export function formatValue(v: Json, unit: Figure["unit"] = null): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) return v.length ? v.map((x) => formatValue(x)).join(", ") : "None";
  if (typeof v === "object") return JSON.stringify(v);
  if (unit === "inr") return formatInr(v);
  if (unit === "percent") return `${v}%`;
  if (unit === "days") return `${v} days`;
  return String(v).replaceAll("_", " ");
}
