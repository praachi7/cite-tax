"use client";

import { useSyncExternalStore } from "react";
import { readRunRaw, subscribeRun } from "./api";
import type { StoredRun } from "./types";

// useSyncExternalStore needs a stable snapshot: re-parse only when the stored string changes.
let cached: { raw: string | null; value: StoredRun | null } = { raw: null, value: null };

function snapshot(): StoredRun | null {
  const raw = readRunRaw();
  if (raw !== cached.raw) {
    let value: StoredRun | null = null;
    try {
      value = raw ? (JSON.parse(raw) as StoredRun) : null;
    } catch {
      value = null;
    }
    cached = { raw, value };
  }
  return cached.value;
}

/** The current run; undefined during the server render, null when nothing has been uploaded yet. */
export function useRun(): StoredRun | null | undefined {
  return useSyncExternalStore(subscribeRun, snapshot, () => undefined);
}
