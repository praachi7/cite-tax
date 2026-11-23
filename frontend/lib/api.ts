import type { ConfigOverrides, EstimateResult, Json, Persona, StoredEstimate } from "./types";

const STORE_KEY = "citetax.estimate";

async function asJson<T>(resp: Response): Promise<T> {
  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    const detail = body?.detail;
    const msg = Array.isArray(detail)
      ? detail.map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ")
      : typeof detail === "string" ? detail : `HTTP ${resp.status}`;
    throw new Error(msg);
  }
  return body as T;
}

export async function getPersonas(): Promise<Persona[]> {
  return asJson<Persona[]>(await fetch("/api/personas"));
}

export async function estimate(input: Record<string, Json>, config: ConfigOverrides): Promise<EstimateResult> {
  const resp = await fetch("/api/tax/estimate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input, config }),
  });
  return asJson<EstimateResult>(resp);
}

export function saveEstimate(e: StoredEstimate): void {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify(e));
  } catch {
    /* storage unavailable: the summary page will say there is nothing to show */
  }
}

export function loadEstimate(): StoredEstimate | null {
  try {
    const raw = sessionStorage.getItem(STORE_KEY);
    return raw ? (JSON.parse(raw) as StoredEstimate) : null;
  } catch {
    return null;
  }
}
