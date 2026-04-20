import { useState, useEffect } from "react";
import { useMeetingStore } from "../store/meetingStore";
import { DirectivesBar } from "./DirectivesBar";
import { DiagramsPanel } from "./DiagramsPanel";
import { AnalysisView } from "./AnalysisView";
import { SpeakerMappingPanel } from "./SpeakerMappingPanel";
import { ActionItemsPanel } from "./ActionItemsPanel";

type AnalysisTab = "auto" | "steered" | "diagrams" | "speakers" | "actions";

export function AnalysisPanel() {
  const analysisTrackA = useMeetingStore((s) => s.analysisTrackA);
  const analysisTrackB = useMeetingStore((s) => s.analysisTrackB);
  const [activeTab, setActiveTab] = useState<AnalysisTab>("auto");

  // Debug log on track A change
  useEffect(() => {
    console.log(
      "[AnalysisPanel] trackA:", analysisTrackA
        ? `stage=${analysisTrackA.stage} cycle=${analysisTrackA.cycle_count}`
        : "null"
    );
  }, [analysisTrackA]);

  const speakerMappings = useMeetingStore((s) => s.speakerMappings);
  const transcriptChunks = useMeetingStore((s) => s.transcriptChunks);

  const hasDiagrams = !!(
    analysisTrackA?.current_state_diagram ||
    analysisTrackA?.mermaid_diagram ||
    analysisTrackB?.mermaid_diagram
  );

  const hasSpeakers = transcriptChunks.some((c) => c.speaker !== null);
  const hasMapping = Object.keys(speakerMappings).length > 0;

  const hasActionItems = [analysisTrackA, analysisTrackB].some((r) =>
    r?.action_items && Object.values(r.action_items).some((arr) => arr.length > 0)
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

        {/* Steered tab */}
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

        {/* Speakers tab */}
        <button
          onClick={() => setActiveTab("speakers")}
          className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
            activeTab === "speakers"
              ? "border-cyan-500 text-slate-100"
              : "border-transparent text-slate-500 hover:text-slate-300"
          }`}
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Speakers
          {(hasSpeakers || hasMapping) && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />}
        </button>

        {/* Actions tab */}
        <button
          onClick={() => setActiveTab("actions")}
          className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
            activeTab === "actions"
              ? "border-orange-500 text-slate-100"
              : "border-transparent text-slate-500 hover:text-slate-300"
          }`}
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Actions
          {hasActionItems && <span className="w-1.5 h-1.5 rounded-full bg-orange-400" />}
        </button>
      </div>

      {/* Tab content */}
      {activeTab === "diagrams" ? (
        <div className="flex-1 min-h-0">
          <DiagramsPanel />
        </div>
      ) : activeTab === "speakers" ? (
        <div className="flex-1 min-h-0">
          <SpeakerMappingPanel />
        </div>
      ) : activeTab === "actions" ? (
        <div className="flex-1 min-h-0">
          <ActionItemsPanel />
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
          <DirectivesBar />
        </div>
      )}
    </div>
  );
}
