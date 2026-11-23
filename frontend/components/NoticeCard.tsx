import type { Notice } from "@/lib/types";
import { Cites } from "./Cites";

/** An "Interpretation uncertain" notice: both readings with citations, the default applied, and the review label. */
export function NoticeCard({ notice, linked = true }: { notice: Notice; linked?: boolean }) {
  return (
    <div className="notice">
      <div className="notice-head">
        <span className="badge warn">Interpretation uncertain</span> <strong>{notice.assumption_id}</strong>
        {notice.result_depends_on_it && <span className="badge">this result depends on it</span>}
      </div>
      <p className="notice-q">{notice.question}</p>
      <ol className="readings">
        {notice.readings.map((r) => (
          <li key={r.key} className={r.is_default ? "reading default" : "reading"}>
            <div>
              <strong>Reading {r.key}</strong>
              {r.is_default && <span className="badge">default applied</span>}
            </div>
            <div>{r.statement}</div>
            <Cites list={r.citations} linked={linked} />
          </li>
        ))}
      </ol>
      {notice.default_reason && <p className="muted"><strong>Why the default:</strong> {notice.default_reason}</p>}
      <p className="muted small">
        Setting: <code>{notice.config_flag}</code>
        {notice.triggered_by.length > 0 && <> · Raised because: {notice.triggered_by.join("; ")}</>}
      </p>
      <p className="not-reviewed">{notice.disclaimer}</p>
    </div>
  );
}
