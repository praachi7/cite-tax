/** Anchor for a citation ID in the sources panel on the same page. */
export function sourceAnchor(id: string): string {
  return "src-" + id.replace(/[^A-Za-z0-9]+/g, "-");
}

/** Citation chips; each links to its passage in the sources panel below. */
export function Cites({ list, linked = true }: { list: string[]; linked?: boolean }) {
  if (!list.length) return <span className="muted">—</span>;
  return (
    <span className="cites">
      {list.map((c) =>
        linked ? (
          <a className="cite" key={c} href={`#${sourceAnchor(c)}`} title="Show the passage in the sources panel">{c}</a>
        ) : (
          <span className="cite" key={c}>{c}</span>
        ),
      )}
    </span>
  );
}
