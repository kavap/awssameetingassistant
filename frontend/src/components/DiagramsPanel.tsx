import { useMeetingStore } from "../store/meetingStore";

function stripMermaidFence(raw: string): string {
  const fenced = raw?.trim().match(/^```(?:mermaid)?\s*\n([\s\S]*?)\n?```\s*$/i);
  return fenced ? fenced[1].trim() : (raw?.trim() ?? "");
}

function isMermaidCode(text: string): boolean {
  const t = text.trim().toLowerCase();
  return (
    t.startsWith("graph ") ||
    t.startsWith("flowchart ") ||
    t.startsWith("sequencediagram") ||
    t.startsWith("classDiagram".toLowerCase()) ||
    t.startsWith("erdiagram") ||
    t.startsWith("gantt")
  );
}

function safeBtoa(str: string): string {
  try {
    return btoa(unescape(encodeURIComponent(str)));
  } catch {
    return "";
  }
}

interface DiagramBlockProps {
  title: string;
  subtitle?: string;
  source: string | undefined;
  accentClass: string;
  emptyMessage: string;
}

function DiagramBlock({ title, subtitle, source, accentClass, emptyMessage }: DiagramBlockProps) {
  const text = stripMermaidFence(source ?? "");
  const valid = text && isMermaidCode(text);
  const encoded = valid ? safeBtoa(text) : "";

  return (
    <div className="border border-slate-700 rounded-lg overflow-hidden">
      {/* Header */}
      <div className={`flex items-center justify-between px-3 py-2 ${accentClass}`}>
        <div>
          <span className="text-xs font-semibold text-slate-100">{title}</span>
          {subtitle && <span className="ml-2 text-xs text-slate-400">{subtitle}</span>}
        </div>
        {encoded && (
          <a
            href={`https://mermaid.live/edit#pako:${encoded}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-300 hover:text-blue-200 transition-colors"
          >
            Open ↗
          </a>
        )}
      </div>

      {/* Content */}
      {valid ? (
        <pre className="bg-slate-900 p-3 text-xs text-slate-300 overflow-x-auto whitespace-pre-wrap leading-relaxed">
          {text}
        </pre>
      ) : (
        <div className="bg-slate-900 px-3 py-4 text-xs text-slate-500 italic text-center">
          {emptyMessage}
        </div>
      )}
    </div>
  );
}

export function DiagramsPanel() {
  const trackA = useMeetingStore((s) => s.analysisTrackA);
  const trackB = useMeetingStore((s) => s.analysisTrackB);

  const noDiagrams =
    !trackA?.current_state_diagram && !trackA?.mermaid_diagram && !trackB?.mermaid_diagram;

  return (
    <div className="flex flex-col h-full min-h-0 overflow-y-auto px-3 py-3 space-y-3">
      {noDiagrams && (
        <div className="flex flex-col items-center justify-center flex-1 text-center px-4 py-8">
          <svg
            className="w-10 h-10 text-slate-700 mb-3"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"
            />
          </svg>
          <p className="text-sm text-slate-500 font-medium">No diagrams yet</p>
          <p className="text-xs text-slate-600 mt-1">
            Diagrams appear at Stage 3 (8+ final segments)
          </p>
        </div>
      )}

      <DiagramBlock
        title="Current State"
        subtitle="customer's existing architecture"
        source={trackA?.current_state_diagram}
        accentClass="bg-slate-800 border-b border-slate-700"
        emptyMessage="Will appear at Stage 3 — shows customer's current environment"
      />

      <DiagramBlock
        title="Future State"
        subtitle="autonomous track"
        source={trackA?.mermaid_diagram}
        accentClass="bg-blue-950/60 border-b border-blue-800"
        emptyMessage="Will appear at Stage 3 — proposed AWS architecture"
      />

      <DiagramBlock
        title="Future State"
        subtitle="steered track"
        source={trackB?.mermaid_diagram}
        accentClass="bg-violet-950/60 border-b border-violet-800"
        emptyMessage={
          trackB
            ? "Steered future state pending — submit a directive to trigger"
            : "No steered track yet — submit an SA directive during the meeting"
        }
      />
    </div>
  );
}
