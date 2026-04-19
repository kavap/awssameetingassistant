import { useState } from "react";

const BACKEND = "http://localhost:8000";

const CANNED_DIRECTIVES = [
  "Serverless preferred",
  "Cost-sensitive customer",
  "Security & compliance first",
  "Focus on migration path",
  "Lift & shift approach",
  "Modernize & re-architect",
  "Competitive displacement",
  "GenAI / Bedrock focus",
  "Multi-region required",
  "Customer is on Azure",
];

export function DirectivesBar() {
  const [input, setInput] = useState("");
  const [sent, setSent] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function sendDirective(directive: string) {
    const d = directive.trim();
    if (!d) return;
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/meeting/directive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ directive: d }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.error ?? `HTTP ${res.status} — start a meeting first`);
        console.warn("[DirectivesBar] directive rejected:", res.status, body);
        return;
      }
      setSent((prev) => [...prev, d]);
      console.log(`[DirectivesBar] directive sent: ${d}`);
    } catch (e) {
      setError("Network error — is the backend running?");
      console.error("[DirectivesBar] fetch error:", e);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    sendDirective(input);
    setInput("");
  }

  return (
    <div className="border-t border-slate-700 px-3 pt-2 pb-3 space-y-2 shrink-0">
      {/* Error message */}
      {error && (
        <p className="text-xs text-red-400">{error}</p>
      )}

      {/* Active directives */}
      {sent.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {sent.map((d, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-violet-900/60 border border-violet-700 text-violet-300 text-xs rounded-full"
            >
              <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              {d}
            </span>
          ))}
        </div>
      )}

      {/* Pre-canned buttons */}
      <div className="flex flex-wrap gap-1">
        {CANNED_DIRECTIVES.map((d) => (
          <button
            key={d}
            onClick={() => sendDirective(d)}
            disabled={sent.includes(d)}
            className="px-2 py-0.5 text-xs bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed text-slate-300 rounded border border-slate-600 transition-colors"
          >
            {d}
          </button>
        ))}
      </div>

      {/* Custom directive input */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Add SA directive (e.g. customer prefers open source)"
          className="flex-1 bg-slate-700 border border-slate-600 text-slate-100 text-xs rounded px-2.5 py-1.5 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
        />
        <button
          type="submit"
          disabled={!input.trim()}
          className="px-3 py-1.5 text-xs bg-violet-700 hover:bg-violet-600 disabled:opacity-40 text-white rounded transition-colors"
        >
          Steer
        </button>
      </form>
    </div>
  );
}
