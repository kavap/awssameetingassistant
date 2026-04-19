import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import { useMeetingStore } from "../store/meetingStore";

// VERSION STAMP — change this string to confirm new code loaded in browser
const DIAGRAMS_VERSION = "v6-debug";
console.log(`[DiagramsPanel] ${DIAGRAMS_VERSION} loaded`);

mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  themeVariables: {
    background: "#0f172a",
    primaryColor: "#1e3a5f",
    primaryTextColor: "#e2e8f0",
    primaryBorderColor: "#334155",
    lineColor: "#64748b",
    secondaryColor: "#1e293b",
    tertiaryColor: "#0f172a",
    edgeLabelBackground: "#1e293b",
    clusterBkg: "#1e293b",
    titleColor: "#94a3b8",
    nodeTextColor: "#e2e8f0",
  },
  flowchart: { curve: "basis", htmlLabels: true },
  securityLevel: "loose",
});

// Global counter for truly unique IDs
let _mermaidIdCounter = 0;

// Global render queue — mermaid uses shared internal state and corrupts with
// concurrent render() calls. Serialise so each waits for the previous to finish.
let _renderQueue: Promise<void> = Promise.resolve();

function enqueueMermaidRender(
  id: string,
  source: string,
  isCancelled: () => boolean,
): Promise<{ svg: string }> {
  return new Promise<{ svg: string }>((resolve, reject) => {
    _renderQueue = _renderQueue.then(async () => {
      if (isCancelled()) { resolve({ svg: "" }); return; }
      try {
        const result = await mermaid.render(id, source);
        resolve(result);
      } catch (err) {
        reject(err);
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Diagram text utilities
// ---------------------------------------------------------------------------

function extractMermaidCode(raw: string): string {
  if (!raw) return "";
  const fenced = raw.trim().match(/^```(?:mermaid)?\s*\n?([\s\S]*?)\n?```\s*$/i);
  let text = fenced ? fenced[1].trim() : raw.trim();
  if (!isMermaidCode(text)) {
    const mermaidStart = text.search(/^(flowchart|graph)\s+(LR|TD|RL|BT)/m);
    if (mermaidStart !== -1) text = text.slice(mermaidStart).trim();
  }
  return text.replace(/\\n/g, " ");
}

/**
 * Mermaid v11 flowchart does NOT support nested subgraphs.
 * Flatten by removing inner subgraph/end wrappers while keeping their nodes.
 */
function flattenNestedSubgraphs(text: string): string {
  const lines = text.split('\n');
  const out: string[] = [];
  let depth = 0;
  let skipEnds = 0;

  for (const line of lines) {
    const t = line.trimStart();
    if (/^subgraph\b/.test(t)) {
      if (depth === 0) {
        out.push(line);
        depth++;
      } else {
        depth++;
        skipEnds++;
      }
    } else if (/^end\s*$/.test(t)) {
      if (skipEnds > 0) {
        skipEnds--;
        depth--;
      } else {
        out.push(line);
        depth = Math.max(0, depth - 1);
      }
    } else {
      out.push(line);
    }
  }
  return out.join('\n');
}

function sanitizeMermaid(raw: string): string {
  let text = raw;
  text = text.replace(/^graph\s+(LR|TD|RL|BT)/m, (_, dir) => `flowchart ${dir}`);
  text = flattenNestedSubgraphs(text);
  text = text.replace(/^(\s*subgraph\s+)([A-Za-z][A-Za-z0-9 _]*)(\s*)$/gm, (_m, prefix, name, trail) => {
    if (!name.includes('[') && name.includes(' ')) {
      const id = name.trim().replace(/\s+/g, '_');
      return `${prefix}${id}["${name.trim()}"]${trail}`;
    }
    return _m;
  });
  const opens = (text.match(/^\s*subgraph\b/gm) || []).length;
  const closes = (text.match(/^\s*end\s*$/gm) || []).length;
  if (opens > closes) text = text + '\n' + 'end\n'.repeat(opens - closes);
  return text;
}

function isMermaidCode(text: string): boolean {
  const t = text.trim().toLowerCase();
  return (
    t.startsWith("graph ") ||
    t.startsWith("flowchart ") ||
    t.startsWith("sequencediagram") ||
    t.startsWith("classdiagram") ||
    t.startsWith("erdiagram") ||
    t.startsWith("gantt")
  );
}

function safeBtoa(str: string): string {
  try { return btoa(unescape(encodeURIComponent(str))); } catch { return ""; }
}

// ---------------------------------------------------------------------------
// MermaidRender
// ---------------------------------------------------------------------------

type RenderStatus = "idle" | "rendering" | "ok" | "error";

interface MermaidRenderProps {
  source: string;
  onStatus?: (s: RenderStatus, detail: string) => void;
}

function MermaidRender({ source, onStatus }: MermaidRenderProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const renderedRef = useRef<string>("");

  useEffect(() => {
    if (!containerRef.current || !source || source === renderedRef.current) return;

    let cancelled = false;
    onStatus?.("rendering", "");

    (async () => {
      const id = `mermaid_diagram_${++_mermaidIdCounter}`;
      const cleanSource = sanitizeMermaid(source);
      console.log(`[MermaidRender #${id}] sanitized (${cleanSource.length} chars):`, cleanSource.slice(0, 120));
      try {
        document.getElementById(id)?.remove();
        const { svg } = await enqueueMermaidRender(id, cleanSource, () => cancelled);
        if (cancelled || !svg) return;
        renderedRef.current = source;
        setError(null);
        onStatus?.("ok", "");
        if (containerRef.current) {
          containerRef.current.innerHTML = svg;
          const svgEl = containerRef.current.querySelector("svg");
          if (svgEl) {
            svgEl.removeAttribute("height");
            svgEl.style.width = "100%";
            svgEl.style.maxWidth = "100%";
          }
        }
      } catch (err) {
        if (cancelled) return;
        const msg = String(err);
        setError(msg);
        onStatus?.("error", msg);
        console.warn(`[MermaidRender #${id}] FAILED:`, msg, "\nSanitized:\n", cleanSource);
      }
    })();

    return () => {
      cancelled = true;
      renderedRef.current = "";
    };
  }, [source]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (error) {
    return (
      <div className="p-3 text-xs bg-red-950/40 border border-red-800 rounded m-2 max-h-[400px] overflow-y-auto">
        <p className="font-bold text-red-300 mb-1">Mermaid render error (open DevTools F12 for full details)</p>
        <p className="text-red-400 mb-2 font-mono break-all">{error.slice(0, 300)}</p>
        <details className="text-slate-400">
          <summary className="cursor-pointer text-slate-500 hover:text-slate-300">Show diagram source</summary>
          <pre className="mt-1 whitespace-pre overflow-x-auto text-slate-400">{source}</pre>
        </details>
      </div>
    );
  }

  return <div ref={containerRef} className="p-3 overflow-x-auto min-h-[60px]" />;
}

// ---------------------------------------------------------------------------
// DiagramBlock
// ---------------------------------------------------------------------------

interface DiagramBlockProps {
  label: string;
  title: string;
  subtitle?: string;
  source: string | undefined;
  accentClass: string;
  emptyMessage: string;
  showDebug: boolean;
}

function DiagramBlock({ label, title, subtitle, source, accentClass, emptyMessage, showDebug }: DiagramBlockProps) {
  const [showSource, setShowSource] = useState(false);
  const [renderStatus, setRenderStatus] = useState<RenderStatus>("idle");
  const [renderDetail, setRenderDetail] = useState("");

  const rawSource = source ?? "";
  const extracted = extractMermaidCode(rawSource);
  const sanitized = extracted ? sanitizeMermaid(extracted) : "";
  const valid = !!(extracted && isMermaidCode(extracted));
  const encoded = valid ? safeBtoa(extracted) : "";

  const statusColor = renderStatus === "ok" ? "text-emerald-400"
    : renderStatus === "error" ? "text-red-400"
    : renderStatus === "rendering" ? "text-yellow-400"
    : "text-slate-500";

  return (
    <div className="border border-slate-700 rounded-lg overflow-hidden">
      {/* Header */}
      <div className={`flex items-center justify-between px-3 py-2 ${accentClass}`}>
        <div>
          <span className="text-xs font-semibold text-slate-100">{title}</span>
          {subtitle && <span className="ml-2 text-xs text-slate-400">{subtitle}</span>}
        </div>
        <div className="flex items-center gap-3">
          {extracted && (
            <button
              onClick={() => setShowSource((v) => !v)}
              className="text-xs text-slate-400 hover:text-slate-200 transition-colors"
            >
              {showSource ? "Hide source" : "Source"}
            </button>
          )}
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
      </div>

      {/* Debug overlay */}
      {showDebug && (
        <div className="bg-slate-950 border-b border-slate-700 px-3 py-2 text-xs font-mono space-y-1">
          <div className="text-slate-500">
            <span className="text-slate-400 font-bold">[{label}]</span>
            {" "}raw={rawSource.length}ch
            {" "}extracted={extracted.length}ch
            {" "}valid=<span className={valid ? "text-emerald-400" : "text-red-400"}>{String(valid)}</span>
            {" "}render=<span className={statusColor}>{renderStatus}</span>
          </div>
          {renderDetail && <div className="text-red-400 break-all">error: {renderDetail.slice(0, 200)}</div>}
          {extracted && (
            <details>
              <summary className="cursor-pointer text-slate-600 hover:text-slate-400">raw→extracted (first 200ch)</summary>
              <pre className="text-slate-500 whitespace-pre-wrap mt-1">{extracted.slice(0, 200)}</pre>
            </details>
          )}
          {sanitized && (
            <details>
              <summary className="cursor-pointer text-slate-600 hover:text-slate-400">after sanitize (first 200ch)</summary>
              <pre className="text-slate-500 whitespace-pre-wrap mt-1">{sanitized.slice(0, 200)}</pre>
            </details>
          )}
        </div>
      )}

      {/* Content */}
      {valid ? (
        <div className="bg-slate-900 max-h-[400px] overflow-y-auto overflow-x-auto">
          {showSource ? (
            <pre className="p-3 text-xs text-slate-300 whitespace-pre leading-relaxed">{extracted}</pre>
          ) : (
            <MermaidRender
              source={extracted}
              onStatus={(s, d) => { setRenderStatus(s); setRenderDetail(d); }}
            />
          )}
        </div>
      ) : (
        <div className="bg-slate-900 max-h-[400px] overflow-y-auto">
          {extracted ? (
            <div>
              <p className="px-3 pt-3 text-xs text-yellow-400">Not recognized as Mermaid — showing raw source:</p>
              <pre className="p-3 text-xs text-slate-400 whitespace-pre leading-relaxed overflow-x-auto">{extracted}</pre>
            </div>
          ) : (
            <div className="px-3 py-4 text-xs text-slate-500 italic text-center">{emptyMessage}</div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DiagramsPanel
// ---------------------------------------------------------------------------

export function DiagramsPanel() {
  const trackA = useMeetingStore((s) => s.analysisTrackA);
  const trackB = useMeetingStore((s) => s.analysisTrackB);
  const [showDebug, setShowDebug] = useState(false);

  const noDiagrams =
    !trackA?.current_state_diagram && !trackA?.mermaid_diagram && !trackB?.mermaid_diagram;

  return (
    <div className="flex flex-col h-full min-h-0 overflow-y-auto px-3 py-3 space-y-3">
      {/* Debug toggle */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-600">{DIAGRAMS_VERSION}</span>
        <button
          onClick={() => setShowDebug((v) => !v)}
          className={`text-xs px-2 py-0.5 rounded transition-colors ${showDebug ? "bg-amber-900/50 text-amber-300" : "text-slate-600 hover:text-slate-400"}`}
        >
          {showDebug ? "Hide debug" : "Debug"}
        </button>
      </div>

      {noDiagrams && !showDebug && (
        <div className="flex flex-col items-center justify-center flex-1 text-center px-4 py-8">
          <svg className="w-10 h-10 text-slate-700 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
          </svg>
          <p className="text-sm text-slate-500 font-medium">No diagrams yet</p>
          <p className="text-xs text-slate-600 mt-1">Diagrams appear at Stage 3 (8+ final segments)</p>
        </div>
      )}

      <DiagramBlock
        label="currentState"
        title="Current State"
        subtitle="customer's existing architecture"
        source={trackA?.current_state_diagram}
        accentClass="bg-slate-800 border-b border-slate-700"
        emptyMessage="Will appear at Stage 3 — shows customer's current environment"
        showDebug={showDebug}
      />
      <DiagramBlock
        label="futureAuto"
        title="Future State"
        subtitle="autonomous track"
        source={trackA?.mermaid_diagram}
        accentClass="bg-blue-950/60 border-b border-blue-800"
        emptyMessage="Will appear at Stage 3 — proposed AWS architecture"
        showDebug={showDebug}
      />
      <DiagramBlock
        label="futureSteered"
        title="Future State"
        subtitle="steered track"
        source={trackB?.mermaid_diagram}
        accentClass="bg-violet-950/60 border-b border-violet-800"
        emptyMessage={
          trackB
            ? "Steered future state pending — submit a directive to trigger"
            : "No steered track yet — submit an SA directive during the meeting"
        }
        showDebug={showDebug}
      />
    </div>
  );
}
