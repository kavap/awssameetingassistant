import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

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

let _mermaidIdCounter = 0;
// Serialise all mermaid.render() calls — mermaid has shared global state
// that corrupts with concurrent calls (e.g. three panels mounting at once).
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
        resolve(await mermaid.render(id, source));
      } catch (err) {
        reject(err);
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Text utilities
// ---------------------------------------------------------------------------

export function isMermaidCode(text: string): boolean {
  const t = text.trim().toLowerCase();
  return (
    t.startsWith("graph ") || t.startsWith("flowchart ") ||
    t.startsWith("sequencediagram") || t.startsWith("classdiagram") ||
    t.startsWith("erdiagram") || t.startsWith("gantt")
  );
}

export function extractMermaidCode(raw: string): string {
  if (!raw) return "";
  const fenced = raw.trim().match(/^```(?:mermaid)?\s*\n?([\s\S]*?)\n?```\s*$/i);
  let text = fenced ? fenced[1].trim() : raw.trim();
  if (!isMermaidCode(text)) {
    const start = text.search(/^(flowchart|graph)\s+(LR|TD|RL|BT)/m);
    if (start !== -1) text = text.slice(start).trim();
  }
  return text.replace(/\\n/g, " ");
}

function flattenNestedSubgraphs(text: string): string {
  const lines = text.split('\n');
  const out: string[] = [];
  let depth = 0, skipEnds = 0;
  for (const line of lines) {
    const t = line.trimStart();
    if (/^subgraph\b/.test(t)) {
      if (depth === 0) { out.push(line); depth++; }
      else { depth++; skipEnds++; }
    } else if (/^end\s*$/.test(t)) {
      if (skipEnds > 0) { skipEnds--; depth--; }
      else { out.push(line); depth = Math.max(0, depth - 1); }
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

export function getMermaidLiveUrl(source: string): string {
  try {
    // mermaid.live #base64: format: base64(JSON.stringify({ code, mermaid }))
    const state = JSON.stringify({
      code: source,
      mermaid: JSON.stringify({ theme: "dark" }),
      autoSync: true,
      updateDiagram: true,
    });
    return `https://mermaid.live/edit#base64:${btoa(unescape(encodeURIComponent(state)))}`;
  } catch {
    return "";
  }
}

// ---------------------------------------------------------------------------
// MermaidRender — low-level render component
// ---------------------------------------------------------------------------

export function MermaidRender({ source }: { source: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const renderedRef = useRef<string>("");

  useEffect(() => {
    if (!containerRef.current || !source || source === renderedRef.current) return;
    let cancelled = false;
    (async () => {
      const id = `mermaid_diagram_${++_mermaidIdCounter}`;
      const cleanSource = sanitizeMermaid(source);
      try {
        document.getElementById(id)?.remove();
        const { svg } = await enqueueMermaidRender(id, cleanSource, () => cancelled);
        if (cancelled || !svg) return;
        renderedRef.current = source;
        setError(null);
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
        console.warn(`[MermaidRender #${id}] FAILED:`, msg, "\nSanitized:\n", cleanSource);
      }
    })();
    return () => { cancelled = true; renderedRef.current = ""; };
  }, [source]);

  if (error) {
    return (
      <div className="p-3 text-xs bg-red-950/40 border border-red-800 rounded m-3">
        <p className="font-bold text-red-300 mb-1">Render error — open DevTools (F12) for details</p>
        <p className="text-red-400 font-mono break-all mb-2">{error.slice(0, 300)}</p>
        <details>
          <summary className="cursor-pointer text-slate-500 hover:text-slate-300">Show source</summary>
          <pre className="mt-1 text-slate-400 whitespace-pre overflow-x-auto text-xs">{source}</pre>
        </details>
      </div>
    );
  }

  return <div ref={containerRef} className="w-full" />;
}

// ---------------------------------------------------------------------------
// DiagramView — full-panel single diagram with toolbar
// ---------------------------------------------------------------------------

export type DiagramTab = "current" | "auto" | "steered";

export const DIAGRAM_TAB_CONFIG: Record<DiagramTab, {
  label: string; sublabel: string; accent: string; activeClass: string;
}> = {
  current: { label: "Current State",  sublabel: "existing",  accent: "border-slate-500",  activeClass: "bg-slate-700 text-slate-100 border-slate-500" },
  auto:    { label: "Future State",   sublabel: "auto",      accent: "border-blue-600",   activeClass: "bg-blue-900/60 text-blue-100 border-blue-600" },
  steered: { label: "Future State",   sublabel: "steered",   accent: "border-violet-600", activeClass: "bg-violet-900/60 text-violet-100 border-violet-600" },
};

export interface DiagramViewProps {
  source: string | undefined;
  tab: DiagramTab;
  hasContent: boolean;
  emptyMessage: string;
}

export function DiagramView({ source, tab, hasContent, emptyMessage }: DiagramViewProps) {
  const [showSource, setShowSource] = useState(false);
  const extracted = extractMermaidCode(source ?? "");
  const valid = !!(extracted && isMermaidCode(extracted));
  const liveUrl = valid ? getMermaidLiveUrl(extracted) : "";
  const { accent } = DIAGRAM_TAB_CONFIG[tab];

  if (!hasContent || !valid) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 text-center px-6 py-12">
        {extracted && !valid ? (
          <>
            <p className="text-xs text-yellow-400 mb-2">Not recognized as Mermaid syntax</p>
            <pre className="text-xs text-slate-500 whitespace-pre-wrap overflow-x-auto max-w-full">{extracted}</pre>
          </>
        ) : (
          <>
            <div className={`w-12 h-12 rounded-full border-2 ${accent} flex items-center justify-center mb-4 opacity-30`}>
              <svg className="w-6 h-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7" />
              </svg>
            </div>
            <p className="text-sm text-slate-500 font-medium">No diagram yet</p>
            <p className="text-xs text-slate-600 mt-1 max-w-xs">{emptyMessage}</p>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex items-center justify-end gap-3 px-3 py-1.5 border-b border-slate-700/50 shrink-0">
        <button
          onClick={() => setShowSource((v) => !v)}
          className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          {showSource ? "Hide source" : "Source"}
        </button>
        {liveUrl && (
          <a
            href={liveUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            Open in Mermaid ↗
          </a>
        )}
      </div>
      <div className="flex-1 overflow-auto p-3">
        {showSource ? (
          <pre className="text-xs text-slate-300 whitespace-pre leading-relaxed">{extracted}</pre>
        ) : (
          <MermaidRender source={extracted} />
        )}
      </div>
    </div>
  );
}
