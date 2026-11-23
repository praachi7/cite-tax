"use client";

import Link from "next/link";
import { useRun } from "@/lib/useRun";
import type { StoredRun } from "@/lib/types";

/** Renders children with the current run, or a pointer back to the upload screen when there is none. */
export function RunGate({ children }: { children: (run: StoredRun) => React.ReactNode }) {
  const run = useRun();
  if (run === undefined) return <p className="muted">Loading…</p>;
  if (run === null) {
    return (
      <div className="panel">
        <p>No estimate yet. Choose a persona and upload a transactions CSV first.</p>
        <Link href="/">Go to Persona &amp; upload</Link>
      </div>
    );
  }
  return (
    <>
      <div className="run-banner">
        <strong>{run.label}</strong> · {run.csv_name} · <span className="badge act">{run.result.estimate.act.label}</span>
      </div>
      {children(run)}
    </>
  );
}
