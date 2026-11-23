import type { AskAnswer, Persona, Source, StoredRun, UploadRequest, UploadResult } from "./types";

export const STORE_KEY = "citetax.run";
const STORE_EVENT = "citetax-run";

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

export async function getPersonaCsv(id: string): Promise<string> {
  const resp = await fetch(`/api/personas/${encodeURIComponent(id)}/transactions.csv`);
  if (!resp.ok) throw new Error(`Could not load the sample CSV for ${id} (HTTP ${resp.status})`);
  return resp.text();
}

export async function uploadEstimate(req: UploadRequest): Promise<UploadResult> {
  const resp = await fetch("/api/tax/estimate/upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return asJson<UploadResult>(resp);
}

export async function getSources(ids: string[]): Promise<Source[]> {
  if (!ids.length) return [];
  const qs = ids.map((i) => `ids=${encodeURIComponent(i)}`).join("&");
  return (await asJson<{ sources: Source[] }>(await fetch(`/api/sources?${qs}`))).sources;
}

export async function ask(question: string, tax_year: number): Promise<AskAnswer> {
  const resp = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, tax_year }),
  });
  return asJson<AskAnswer>(resp);
}

// ---- the current run, kept in sessionStorage so every screen reads the same upload ----

export function saveRun(run: StoredRun): void {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify(run));
  } catch {
    /* storage unavailable or full: screens will say there is nothing to show */
  }
  window.dispatchEvent(new Event(STORE_EVENT));
}

export function readRunRaw(): string | null {
  try {
    return sessionStorage.getItem(STORE_KEY);
  } catch {
    return null;
  }
}

export function subscribeRun(cb: () => void): () => void {
  window.addEventListener(STORE_EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(STORE_EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}
