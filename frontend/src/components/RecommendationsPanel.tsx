import { useState } from "react";
import { useMeetingStore } from "../store/meetingStore";
import { RecommendationCard } from "./RecommendationCard";

const BACKEND = "http://localhost:8000";

export function RecommendationsPanel() {
  const recommendations = useMeetingStore((s) => s.recommendations);
  const ccmState = useMeetingStore((s) => s.ccmState);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);

  async function handleAsk() {
    if (!question.trim()) return;
    setAsking(true);
    try {
      await fetch(`${BACKEND}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      setQuestion("");
    } finally {
      setAsking(false);
    }
  }

  const awsServices = Object.values(ccmState?.mentioned_services ?? {}).filter(
    (s) => s.category === "aws"
  );
  const competitors = Object.values(ccmState?.mentioned_services ?? {}).filter(
    (s) => s.category === "competitor"
  );

  return (
    <div className="flex flex-col h-full">
      {/* Context summary */}
      {ccmState && (
        <div className="px-3 py-2 border-b border-slate-700 space-y-1.5">
          {ccmState.active_topics.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {ccmState.active_topics.slice(0, 4).map((t) => (
                <span
                  key={t.name}
                  className="text-xs px-1.5 py-0.5 bg-slate-700 text-slate-300 rounded"
                >
                  {t.name.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          )}
          <div className="flex gap-3 text-xs text-slate-500">
            {awsServices.length > 0 && (
              <span>
                <span className="text-blue-400">AWS:</span>{" "}
                {awsServices
                  .sort((a, b) => b.mention_count - a.mention_count)
                  .slice(0, 4)
                  .map((s) => s.name)
                  .join(", ")}
              </span>
            )}
            {competitors.length > 0 && (
              <span>
                <span className="text-amber-400">Other:</span>{" "}
                {competitors.map((s) => s.name).join(", ")}
              </span>
            )}
          </div>
          {ccmState.open_questions.length > 0 && (
            <div className="text-xs text-slate-500">
              <span className="text-yellow-400">
                {ccmState.open_questions.length} open Q
                {ccmState.open_questions.length > 1 ? "s" : ""}
              </span>
              {": "}
              {ccmState.open_questions[0].text.slice(0, 60)}
              {ccmState.open_questions[0].text.length > 60 ? "…" : ""}
            </div>
          )}
        </div>
      )}

      {/* Recommendations feed */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {recommendations.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-slate-600 text-sm gap-2">
            <svg className="w-8 h-8 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <span>Waiting for conversation context...</span>
          </div>
        ) : (
          recommendations.map((card) => (
            <RecommendationCard key={card.id} card={card} />
          ))
        )}
      </div>

      {/* Manual ask input */}
      <div className="border-t border-slate-700 p-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAsk()}
            placeholder="Ask a question to trigger recommendations..."
            className="flex-1 bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={handleAsk}
            disabled={asking || !question.trim()}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 text-white text-sm rounded transition-colors"
          >
            Ask
          </button>
        </div>
      </div>
    </div>
  );
}
