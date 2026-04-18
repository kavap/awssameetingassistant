import { useState } from "react";
import type { RecommendationCard as IRecommendationCard } from "../types";
import { useMeetingStore } from "../store/meetingStore";

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.7 ? "bg-emerald-500" : value >= 0.4 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-500 tabular-nums w-8">{pct}%</span>
    </div>
  );
}

interface Props {
  card: IRecommendationCard;
}

export function RecommendationCard({ card }: Props) {
  const [expanded, setExpanded] = useState(false);
  const dismiss = useMeetingStore((s) => s.dismissRecommendation);

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-sm space-y-2 animate-fade-in">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap gap-1">
          {card.service_mentioned.slice(0, 3).map((svc) => (
            <span
              key={svc}
              className="inline-block text-xs px-1.5 py-0.5 bg-blue-900/60 text-blue-300 rounded border border-blue-700/50"
            >
              {svc}
            </span>
          ))}
        </div>
        <button
          onClick={() => dismiss(card.id)}
          className="text-slate-600 hover:text-slate-400 shrink-0 mt-0.5"
          aria-label="Dismiss"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Title */}
      <p className="font-semibold text-slate-100 leading-snug">{card.title}</p>

      {/* Summary */}
      <p className="text-slate-400 leading-relaxed">{card.summary}</p>

      {/* Confidence */}
      <ConfidenceBar value={card.confidence} />

      {/* Action items (expandable) */}
      {card.action_items.length > 0 && (
        <div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            <svg
              className={`w-3 h-3 transition-transform ${expanded ? "rotate-90" : ""}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            {expanded ? "Hide" : "Show"} talking points ({card.action_items.length})
          </button>
          {expanded && (
            <ul className="mt-2 space-y-1 pl-3">
              {card.action_items.map((item, i) => (
                <li key={i} className="text-slate-400 text-xs flex gap-1.5">
                  <span className="text-blue-500 shrink-0">•</span>
                  {item}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Source links */}
      {card.source_urls.length > 0 && (
        <div className="flex flex-wrap gap-2 pt-1 border-t border-slate-700">
          {card.source_urls.slice(0, 3).map((url, i) => (
            <a
              key={i}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-400 hover:text-blue-300 hover:underline truncate max-w-[180px]"
              title={url}
            >
              ↗ {new URL(url).hostname.replace("www.", "")}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
