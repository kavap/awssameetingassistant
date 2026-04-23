import ReactMarkdown from "react-markdown";
import type { AnalysisResult } from "../types";

const STAGE_CONFIG = {
  1: { label: "Gathering Context", color: "text-yellow-400", bg: "bg-yellow-900/30 border-yellow-700" },
  2: { label: "Building Picture",  color: "text-blue-400",   bg: "bg-blue-900/30 border-blue-700"   },
  3: { label: "Ready",             color: "text-emerald-400", bg: "bg-emerald-900/30 border-emerald-700" },
} as const;

/** Render a markdown string with consistent dark-theme prose styling. */
function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      components={{
        p:      ({ children }) => <p className="text-xs text-slate-300 leading-relaxed mb-1.5 last:mb-0">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold text-slate-100">{children}</strong>,
        em:     ({ children }) => <em className="italic text-slate-400">{children}</em>,
        ul:     ({ children }) => <ul className="list-disc list-outside pl-4 space-y-0.5 mb-1.5">{children}</ul>,
        ol:     ({ children }) => <ol className="list-decimal list-outside pl-4 space-y-0.5 mb-1.5">{children}</ol>,
        li:     ({ children }) => <li className="text-xs text-slate-300 leading-relaxed">{children}</li>,
        h1:     ({ children }) => <h1 className="text-sm font-semibold text-slate-200 mt-2 mb-1">{children}</h1>,
        h2:     ({ children }) => <h2 className="text-xs font-semibold text-slate-200 mt-2 mb-1 uppercase tracking-wide">{children}</h2>,
        h3:     ({ children }) => <h3 className="text-xs font-semibold text-slate-300 mt-1.5 mb-0.5">{children}</h3>,
        code:   ({ children }) => <code className="text-xs font-mono bg-slate-800 text-emerald-300 px-1 py-0.5 rounded">{children}</code>,
        pre:    ({ children }) => <pre className="text-xs font-mono bg-slate-800 text-emerald-300 p-2 rounded overflow-x-auto mb-1.5">{children}</pre>,
        a:      ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener noreferrer"
            className="text-blue-400 hover:text-blue-300 hover:underline">
            {children}
          </a>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-slate-600 pl-3 italic text-slate-400 my-1">
            {children}
          </blockquote>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}

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
        <Markdown>{text}</Markdown>
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
