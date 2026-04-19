import type { AnalysisResult } from "../types";

const STAGE_CONFIG = {
  1: { label: "Gathering Context", color: "text-yellow-400", bg: "bg-yellow-900/30 border-yellow-700" },
  2: { label: "Building Picture", color: "text-blue-400",   bg: "bg-blue-900/30 border-blue-700"   },
  3: { label: "Ready",            color: "text-emerald-400", bg: "bg-emerald-900/30 border-emerald-700" },
} as const;

function Section({ title, content }: { title: string; content: string }) {
  const text = content?.trim();
  if (!text) return null;
  const isGathering = text.startsWith("Gathering context");
  return (
    <div className="mb-3">
      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">{title}</h4>
      {isGathering ? (
        <p className="text-xs text-slate-500 italic">{text}</p>
      ) : (
        <div className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{text}</div>
      )}
    </div>
  );
}

function SourcesList({ sources }: { sources: string[] }) {
  if (!sources.length) return null;
  return (
    <div className="mb-3">
      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Sources</h4>
      <ul className="space-y-0.5">
        {sources.map((url, i) => {
          let domain = url;
          try { domain = new URL(url).hostname; } catch { /* ignore */ }
          return (
            <li key={i}>
              <a href={url} target="_blank" rel="noopener noreferrer"
                className="text-xs text-blue-400 hover:text-blue-300 hover:underline truncate block" title={url}>
                {domain}
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function AnalysisView({ result }: { result: AnalysisResult }) {
  const stageKey = (result.stage as number) in STAGE_CONFIG ? result.stage as 1 | 2 | 3 : 1;
  const stage = STAGE_CONFIG[stageKey];
  return (
    <div className="animate-fade-in">
      <div className={`flex items-center gap-2 px-2 py-1 rounded border text-xs mb-3 ${stage.bg}`}>
        <span className={`font-semibold ${stage.color}`}>{stage.label}</span>
        <span className="text-slate-500">·</span>
        <span className="text-slate-500">Cycle {result.cycle_count}</span>
        {result.segment_count !== undefined && (
          <>
            <span className="text-slate-500">·</span>
            <span className="text-slate-500">{result.segment_count} segs</span>
          </>
        )}
        {result.is_steered && (
          <>
            <span className="text-slate-500">·</span>
            <span className="text-violet-400 font-medium">Steered</span>
          </>
        )}
      </div>
      {result.stage === 1 && result.reasoning && (
        <div className="mb-3 text-xs text-slate-500 italic bg-slate-800 rounded p-2 border border-slate-700">
          {result.reasoning}
        </div>
      )}
      <Section title="Situation"             content={result.situation} />
      <Section title="Current State"         content={result.current_state} />
      <Section title="Customer Needs"        content={result.customer_needs} />
      <Section title="Open Questions"        content={result.open_questions} />
      <Section title="Proposed Architecture" content={result.proposed_architecture} />
      <Section title="Key Recommendations"   content={result.key_recommendations} />
      <SourcesList sources={result.sources ?? []} />
    </div>
  );
}
