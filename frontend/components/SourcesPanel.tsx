"use client";

import { useEffect, useState } from "react";
import { getSources } from "@/lib/api";
import type { Notice, Source } from "@/lib/types";
import { sourceAnchor } from "./Cites";
import { NoticeCard } from "./NoticeCard";

const MAX_IDS = 60; // the API's limit per request

interface Loaded {
  key: string;
  sources: Source[];
  error: string | null;
}

/** Sources and notices panel (SRS/SDS 3.5): the cited passages on this screen, then the interpretation notices. */
export function SourcesPanel({ ids, notices }: { ids: string[]; notices: Notice[] }) {
  const all = [...new Set([...ids, ...notices.flatMap((n) => n.readings.flatMap((r) => r.citations))])].sort();
  const shown = all.slice(0, MAX_IDS);
  const key = shown.join("|");
  const [loaded, setLoaded] = useState<Loaded>({ key: "", sources: [], error: null });

  useEffect(() => {
    let live = true;
    getSources(key ? key.split("|") : [])
      .then((sources) => live && setLoaded({ key, sources, error: null }))
      .catch((e: Error) => live && setLoaded({ key, sources: [], error: e.message }));
    return () => {
      live = false;
    };
  }, [key]);

  const loading = loaded.key !== key;

  return (
    <section className="sources-panel" aria-labelledby="sources-h">
      <h2 id="sources-h">Sources and notices</h2>

      {notices.length > 0 && (
        <>
          <h3>Interpretation uncertain</h3>
          {notices.map((n) => <NoticeCard key={n.assumption_id} notice={n} />)}
        </>
      )}

      <h3>Cited passages ({all.length})</h3>
      {all.length > shown.length && <p className="muted">Showing the first {shown.length} of {all.length} citations.</p>}
      {loading && <p className="muted">Loading passages…</p>}
      {loaded.error && <p className="error">Could not load passages: {loaded.error}</p>}
      {!loading && loaded.sources.map((s) => (
        <details key={s.id} id={sourceAnchor(s.id)} className="panel source">
          <summary>
            <code>{s.id}</code> {s.label !== s.id && <span className="muted">{s.label}</span>}
            {!s.resolved && <span className="badge warn">not in the corpus</span>}
            {s.resolved && s.reviewed === false && <span className="badge">not yet hand-reviewed</span>}
          </summary>
          {s.resolved ? (
            <>
              <p className="muted small">{s.breadcrumb}{s.chunk_id !== s.id && <> · passage <code>{s.chunk_id}</code></>}</p>
              {s.heading && <p><strong>{s.heading}</strong></p>}
              <pre className="passage">{s.text}</pre>
            </>
          ) : (
            <p className="muted">
              This citation has no passage in the curated corpus (for example a secondary source carried as a source
              note). It is shown as cited, not as verified.
            </p>
          )}
        </details>
      ))}
    </section>
  );
}
