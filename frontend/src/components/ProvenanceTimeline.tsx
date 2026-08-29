// Phase 14: a visual decision-provenance timeline, built ONLY from the real
// audit timeline (GET /exceptions/{id}/provenance) -- no invented
// timestamps or stages, and no stage rendered that the API didn't return.
import type { TimelineEntry } from "../api/types";
import { formatDateTime, titleCase } from "../lib/format";

export function ProvenanceTimeline({ timeline }: { timeline: TimelineEntry[] }) {
  if (timeline.length === 0) {
    return <p className="muted">No audit timeline is available for this exception.</p>;
  }

  return (
    <ol className="provenance-timeline">
      {timeline.map((entry, i) => (
        <li key={`${entry.event_type}-${i}`} className="provenance-timeline__item">
          <div className="provenance-timeline__marker" aria-hidden="true" />
          <div className="provenance-timeline__content">
            <span className="provenance-timeline__event">{titleCase(entry.event_type)}</span>
            <span className="provenance-timeline__meta">
              {formatDateTime(entry.timestamp)} · {titleCase(entry.actor_type)}
              {entry.actor_id ? ` (${entry.actor_id})` : ""}
            </span>
          </div>
        </li>
      ))}
    </ol>
  );
}
