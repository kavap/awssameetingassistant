import { useState, useEffect } from "react";
import { useMeetingStore } from "../store/meetingStore";
import { DirectivesBar } from "./DirectivesBar";
import { DiagramsPanel } from "./DiagramsPanel";
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

function AnalysisView({ result }: { result: AnalysisResult }) {
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
      <Section title="Situation"           content={result.situation} />
      <Section title="Current State"       content={result.current_state} />
      <Section title="Customer Needs"      content={result.customer_needs} />
      <Section title="Open Questions"      content={result.open_questions} />
      <Section title="Proposed Architecture" content={result.proposed_architecture} />
      <Section title="Key Recommendations" content={result.key_recommendations} />
      <SourcesList sources={result.sources ?? []} />
    </div>
  );
}

type AnalysisTab = "auto" | "steered" | "diagrams";

export function AnalysisPanel() {
  const analysisTrackA = useMeetingStore((s) => s.analysisTrackA);
  const analysisTrackB = useMeetingStore((s) => s.analysisTrackB);
  const [activeTab, setActiveTab] = useState<AnalysisTab>("auto");

  // Log changes for debugging
  useEffect(() => {
    console.log(
      "[AnalysisPanel] trackA:", analysisTrackA
        ? `stage=${analysisTrackA.stage} cycle=${analysisTrackA.cycle_count}`
        : "null"
    );
  }, [analysisTrackA]);

  const hasDiagrams = !!(
    analysisTrackA?.current_state_diagram ||
    analysisTrackA?.mermaid_diagram ||
    analysisTrackB?.mermaid_diagram
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Panel header + tabs — single row */}
      <div className="flex items-center border-b border-slate-700 shrink-0 px-2 gap-2">
        <div className="flex items-center gap-1.5 mr-1">
          <svg className="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider whitespace-nowrap">Live Analysis</span>
        </div>
        <div className="w-px h-4 bg-slate-700 shrink-0" />
        {/* Auto tab */}
        <button
          onClick={() => setActiveTab("auto")}
          className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
            activeTab === "auto"
              ? "border-blue-500 text-slate-100"
              : "border-transparent text-slate-500 hover:text-slate-300"
          }`}
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          Auto
        </button>

        {/* Steered tab — always visible, dimmed when no track B */}
        <button
          onClick={() => setActiveTab("steered")}
          className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
            activeTab === "steered"
              ? "border-violet-500 text-slate-100"
              : "border-transparent text-slate-500 hover:text-slate-300"
          }`}
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          Steered
          {analysisTrackB && <span className="w-1.5 h-1.5 rounded-full bg-violet-400" />}
        </button>

        {/* Diagrams tab */}
        <button
          onClick={() => setActiveTab("diagrams")}
          className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
            activeTab === "diagrams"
              ? "border-emerald-500 text-slate-100"
              : "border-transparent text-slate-500 hover:text-slate-300"
          }`}
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
          </svg>
          Diagrams
          {hasDiagrams && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />}
        </button>
      </div>

      {/* Tab content */}
      {activeTab === "diagrams" ? (
        <div className="flex-1 min-h-0">
          <DiagramsPanel />
        </div>
      ) : (
        <div className="flex flex-col flex-1 min-h-0">
          <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2">
            {activeTab === "auto" ? (
              analysisTrackA ? (
                <AnalysisView result={analysisTrackA} />
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center px-4">
                  <div className="w-10 h-10 bg-slate-800 rounded-full flex items-center justify-center mb-3">
                    <svg className="w-5 h-5 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                        d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                  </div>
                  <p className="text-xs text-slate-500">Analysis appears after the first few transcript segments.</p>
                </div>
              )
            ) : (
              /* Steered tab */
              analysisTrackB ? (
                <AnalysisView result={analysisTrackB} />
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center px-4">
                  <div className="w-10 h-10 bg-slate-800 rounded-full flex items-center justify-center mb-3">
                    <svg className="w-5 h-5 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                        d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                  <p className="text-xs text-slate-500">Submit an SA directive to generate a steered analysis track.</p>
                </div>
              )
            )}
          </div>

          {/* Directives bar — only on analysis tabs, not diagrams */}
          <DirectivesBar />
        </div>
      )}
    </div>
  );
}
