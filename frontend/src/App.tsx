import { Component, useState } from "react";
import type { ReactNode } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useMeetingStore } from "./store/meetingStore";
import { TranscriptPanel } from "./components/TranscriptPanel";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { StartMeetingModal } from "./components/StartMeetingModal";
import { PastMeetingsDrawer } from "./components/PastMeetingsDrawer";
import type { MeetingType } from "./types";
import "./index.css";

class PanelErrorBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(e: Error) {
    return { error: e.message };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="flex flex-col items-center justify-center h-full text-center px-4">
          <p className="text-xs text-red-400 mb-2">Panel render error</p>
          <p className="text-xs text-slate-600 font-mono">{this.state.error}</p>
          <button
            onClick={() => this.setState({ error: null })}
            className="mt-3 px-3 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

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
  useWebSocket();

  const connectionStatus = useMeetingStore((s) => s.connectionStatus);
  const meetingStatus = useMeetingStore((s) => s.meetingStatus);
  const analysisTrackA = useMeetingStore((s) => s.analysisTrackA);

  const [showModal, setShowModal] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  async function startMeeting(customerId: string, meetingType: MeetingType) {
    setShowModal(false);
    await fetch(`${BACKEND}/meeting/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customer_id: customerId, meeting_type: meetingType }),
    });
  }

  async function stopMeeting() {
    // Snapshot full state before stop clears backend session
    const state = useMeetingStore.getState();
    const snapshot = {
      session_id: state.sessionId,
      customer_id: state.customerId,
      meeting_type: state.meetingType,
      started_at: state.meetingStartedAt ?? Date.now() / 1000,
      stopped_at: Date.now() / 1000,
      transcript: state.transcriptChunks,
      analysis_track_a: state.analysisTrackA,
      analysis_track_b: state.analysisTrackB,
      recommendations: state.recommendations,
    };

    await fetch(`${BACKEND}/meeting/stop`, { method: "POST" });

    if (snapshot.session_id) {
      fetch(`${BACKEND}/meetings/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(snapshot),
      }).catch((e) => console.warn("[App] Failed to save meeting:", e));
    }
  }

  const isRecording = meetingStatus === "recording";
  const stage = analysisTrackA?.stage ?? null;

  return (
    <div className="flex flex-col h-screen bg-slate-900 text-slate-200">
      {/* Header */}
      <header className="flex items-center gap-3 px-4 py-2 border-b border-slate-700 bg-slate-900/90 backdrop-blur shrink-0">
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

        {/* Recording + stage indicator */}
        {isRecording && (
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 text-xs text-red-400">
              <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
              LIVE
            </div>
            {stage && (
              <span className={`text-xs px-2 py-0.5 rounded-full border ${
                stage === 3
                  ? "text-emerald-400 bg-emerald-900/30 border-emerald-700"
                  : stage === 2
                  ? "text-blue-400 bg-blue-900/30 border-blue-700"
                  : "text-yellow-400 bg-yellow-900/30 border-yellow-700"
              }`}>
                Stage {stage}
              </span>
            )}
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <StatusDot status={connectionStatus} />
            {connectionStatus}
          </div>

          {/* Past Meetings button */}
          <button
            onClick={() => setShowHistory(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-slate-100 text-xs font-medium rounded transition-colors border border-slate-700"
            title="View past meetings"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            History
          </button>

          {!isRecording ? (
            <button
              onClick={() => setShowModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-xs font-medium rounded transition-colors"
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
        {/* Left: Transcript (55%) */}
        <div className="flex flex-col w-[55%] border-r border-slate-700 min-h-0">
          <TranscriptPanel />
        </div>

        {/* Right: Live Analysis (45%) */}
        <div className="flex flex-col w-[45%] min-h-0">
          <PanelErrorBoundary>
            <AnalysisPanel />
          </PanelErrorBoundary>
        </div>
      </div>

      {/* Start Meeting Modal */}
      {showModal && (
        <StartMeetingModal
          onConfirm={startMeeting}
          onCancel={() => setShowModal(false)}
        />
      )}

      {/* Past Meetings Drawer */}
      <PastMeetingsDrawer
        open={showHistory}
        onClose={() => setShowHistory(false)}
      />
    </div>
  );
}
