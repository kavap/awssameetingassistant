import { useState } from "react";
import { useMeetingStore } from "../store/meetingStore";
import {
  DiagramView,
  DIAGRAM_TAB_CONFIG,
  type DiagramTab,
} from "./MermaidRender";

export function DiagramsPanel() {
  const trackA = useMeetingStore((s) => s.analysisTrackA);
  const trackB = useMeetingStore((s) => s.analysisTrackB);
  const [activeTab, setActiveTab] = useState<DiagramTab>("current");

  const sources: Record<DiagramTab, string | undefined> = {
    current: trackA?.current_state_diagram,
    auto:    trackA?.mermaid_diagram,
    steered: trackB?.mermaid_diagram,
  };

  const hasContent: Record<DiagramTab, boolean> = {
    current: !!trackA?.current_state_diagram,
    auto:    !!trackA?.mermaid_diagram,
    steered: !!trackB?.mermaid_diagram,
  };

  const emptyMessages: Record<DiagramTab, string> = {
    current: "Appears at Stage 3 — customer's current environment",
    auto:    "Appears at Stage 3 — proposed AWS architecture",
    steered: trackB
      ? "Submit a directive to generate a steered future state"
      : "Submit an SA directive during the meeting to enable this track",
  };

  const tabs: DiagramTab[] = ["current", "auto", "steered"];

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Tab bar */}
      <div className="flex items-center gap-1 px-2 pt-2 pb-0 border-b border-slate-700 shrink-0">
        {tabs.map((tab) => {
          const cfg = DIAGRAM_TAB_CONFIG[tab];
          const isActive = activeTab === tab;
          const hasDot = hasContent[tab];
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`relative flex items-center gap-1 px-3 py-1.5 text-xs rounded-t border-b-2 transition-colors ${
                isActive
                  ? cfg.activeClass
                  : "text-slate-500 hover:text-slate-300 border-transparent"
              }`}
            >
              <span className="font-medium">{cfg.label}</span>
              <span className={`text-[10px] ${isActive ? "opacity-70" : "opacity-50"}`}>{cfg.sublabel}</span>
              {hasDot && (
                <span className={`w-1.5 h-1.5 rounded-full ml-0.5 ${
                  tab === "steered" ? "bg-violet-400" : tab === "auto" ? "bg-blue-400" : "bg-slate-400"
                }`} />
              )}
            </button>
          );
        })}
      </div>

      {/* Full-panel diagram */}
      <DiagramView
        source={sources[activeTab]}
        tab={activeTab}
        hasContent={hasContent[activeTab]}
        emptyMessage={emptyMessages[activeTab]}
      />
    </div>
  );
}
