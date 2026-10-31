import type { Source } from "@/lib/types";

export function SourceCard({ source, verifiedQuote = false }: { source: Source; verifiedQuote?: boolean }) {
  const isCurated = source.source_type === "curated";
  return (
    <article className="source-card">
      <div className="source-topline">
        <span className="source-type">{source.source_type}</span>
        <span className="source-rank" aria-label={`Source rank ${Math.round(source.rank_score * 100)} percent`}>
          rank {Math.round(source.rank_score * 100)}
        </span>
      </div>
      <h4>{source.title || source.domain}</h4>
      <p>{source.domain}</p>
      <div className="source-footer">
        <span className={verifiedQuote ? "quote-badge verified" : "quote-badge"}>
          <span aria-hidden="true">{verifiedQuote ? "✓" : "○"}</span>
          {verifiedQuote ? "Verified quote" : "Source captured"}
        </span>
        {isCurated ? (
          <span className="source-origin">Stored corpus</span>
        ) : (
          <a href={source.url} target="_blank" rel="noopener noreferrer" aria-label={`Open source: ${source.title || source.domain}`}>
            Open ↗
          </a>
        )}
      </div>
    </article>
  );
}
