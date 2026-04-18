import { useWebSocket } from "./hooks/useWebSocket";
import { useMeetingStore } from "./store/meetingStore";
import { TranscriptPanel } from "./components/TranscriptPanel";
import { RecommendationsPanel } from "./components/RecommendationsPanel";
import "./index.css";

const BACKEND = "http://localhost:8000";

function StatusDot({ status }: { status: string }) {
  const color =
    status === "connected"
      ? "bg-emerald-500"
      : status === "connecting"
      ? "bg-yellow-500 animate-pulse"
      : "bg-red-500";
  return <span className={`inline-block w-2 h-2 rounded-full ${color}`} />;
}

export default function App() {
  useWebSocket(); // establish WS connection

  const connectionStatus = useMeetingStore((s) => s.connectionStatus);
  const meetingStatus = useMeetingStore((s) => s.meetingStatus);

  async function startMeeting() {
    await fetch(`${BACKEND}/meeting/start`, { method: "POST" });
  }

  async function stopMeeting() {
    await fetch(`${BACKEND}/meeting/stop`, { method: "POST" });
  }

  const isRecording = meetingStatus === "recording";

  return (
    <div className="flex flex-col h-screen bg-slate-900 text-slate-200">
      {/* Header */}
      <header className="flex items-center gap-3 px-4 py-2 border-b border-slate-700 bg-slate-900/90 backdrop-blur shrink-0">
        {/* Logo / title */}
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 bg-blue-600 rounded flex items-center justify-center">
            <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <span className="font-semibold text-slate-100 text-sm">
            AWS Meeting Intelligence
          </span>
        </div>

        {/* Recording indicator */}
        {isRecording && (
          <div className="flex items-center gap-1.5 text-xs text-red-400">
            <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
            LIVE
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          {/* WS status */}
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <StatusDot status={connectionStatus} />
            {connectionStatus}
          </div>

          {/* Start / Stop */}
          {!isRecording ? (
            <button
              onClick={startMeeting}
              disabled={connectionStatus !== "connected"}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-500 disabled:bg-slate-700 disabled:text-slate-500 text-white text-xs font-medium rounded transition-colors"
            >
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" />
              </svg>
              Start Meeting
            </button>
          ) : (
            <button
              onClick={stopMeeting}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-xs font-medium rounded transition-colors"
            >
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                <rect x="4" y="4" width="16" height="16" rx="2" />
              </svg>
              Stop
            </button>
          )}
        </div>
      </header>

      {/* Main two-column layout */}
      <div className="flex flex-1 min-h-0">
        {/* Left: Transcript (60%) */}
        <div className="flex flex-col w-3/5 border-r border-slate-700 min-h-0">
          <TranscriptPanel />
        </div>

        {/* Right: Recommendations (40%) */}
        <div className="flex flex-col w-2/5 min-h-0">
          <div className="px-3 py-2 border-b border-slate-700 flex items-center gap-2">
            <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Recommendations
            </span>
          </div>
          <div className="flex-1 min-h-0 flex flex-col">
            <RecommendationsPanel />
          </div>
        </div>
      </div>
    </div>
  );
}
