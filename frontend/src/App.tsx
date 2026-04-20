import { Component, useState, useRef, useCallback, useEffect } from "react";
import type { ReactNode } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useMeetingStore } from "./store/meetingStore";
import { TranscriptPanel } from "./components/TranscriptPanel";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { StartMeetingModal } from "./components/StartMeetingModal";
import { PastMeetingsDrawer } from "./components/PastMeetingsDrawer";
import type { MeetingType, SpeakerMappings } from "./types";
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

  const setOwnerParticipant = useMeetingStore((s) => s.setOwnerParticipant);

  // Fetch owner profile once on startup so it's available in the Speakers tab
  // before the Start Meeting modal is ever opened.
  useEffect(() => {
    fetch(`${BACKEND}/meeting/config`)
      .then((r) => r.json())
      .then((data: { owner_participant?: string }) => {
        if (data.owner_participant) setOwnerParticipant(data.owner_participant);
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const connectionStatus = useMeetingStore((s) => s.connectionStatus);
  const meetingStatus = useMeetingStore((s) => s.meetingStatus);
  const analysisTrackA = useMeetingStore((s) => s.analysisTrackA);

  const [showModal, setShowModal] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  // Resizable split — transcript left, analysis right (clamped 20–80%)
  const [splitPct, setSplitPct] = useState(55);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const onDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMouseMove = (mv: MouseEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const { left, width } = containerRef.current.getBoundingClientRect();
      const pct = ((mv.clientX - left) / width) * 100;
      setSplitPct(Math.min(80, Math.max(20, pct)));
    };

    const onMouseUp = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }, []);

  async function startMeeting(
    customerId: string,
    meetingType: MeetingType,
    meetingName: string,
    participants: string[],
    selectedRoles: string[],
  ) {
    setShowModal(false);
    await fetch(`${BACKEND}/meeting/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_id: customerId,
        meeting_type: meetingType,
        meeting_name: meetingName,
        participants,
        selected_roles: selectedRoles,
      }),
    });
  }

  async function stopMeeting() {
    // Snapshot full state before stop clears backend session
    const state = useMeetingStore.getState();
    const snapshot = {
      session_id: state.sessionId,
      customer_id: state.customerId,
      meeting_type: state.meetingType,
      meeting_name: state.meetingName,
      started_at: state.meetingStartedAt ?? Date.now() / 1000,
      stopped_at: Date.now() / 1000,
      transcript: state.transcriptChunks,
      analysis_track_a: state.analysisTrackA,
      analysis_track_b: state.analysisTrackB,
      recommendations: state.recommendations,
      participants: state.participants,
      selected_roles: state.selectedRoles,
      speaker_mapping: state.speakerMappings as SpeakerMappings,
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

  const STAGE_LABELS: Record<number, string> = {
    1: "Gathering context",
    2: "Direction emerging",
    3: "Full picture",
  };

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
              <span className={`flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full border ${
                stage === 3
                  ? "text-emerald-400 bg-emerald-900/30 border-emerald-700"
                  : stage === 2
                  ? "text-blue-400 bg-blue-900/30 border-blue-700"
                  : "text-yellow-400 bg-yellow-900/30 border-yellow-700"
              }`}>
                <span className="font-medium">Stage {stage}</span>
                <span className="opacity-60">·</span>
                <span className="opacity-75">{STAGE_LABELS[stage]}</span>
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

      {/* Main two-column layout — resizable */}
      <div ref={containerRef} className="flex flex-1 min-h-0 relative">
        {/* Left: Transcript */}
        <div className="flex flex-col min-h-0 min-w-0" style={{ width: `${splitPct}%` }}>
          <TranscriptPanel />
        </div>

        {/* Drag handle */}
        <div
          onMouseDown={onDividerMouseDown}
          className="w-1 shrink-0 bg-slate-700 hover:bg-blue-500 cursor-col-resize transition-colors active:bg-blue-400 relative group"
          title="Drag to resize"
        >
          {/* Wider invisible hit target */}
          <div className="absolute inset-y-0 -left-1 -right-1" />
          {/* Visual grip dots */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col gap-0.5 opacity-0 group-hover:opacity-60 transition-opacity pointer-events-none">
            {[0, 1, 2].map((i) => (
              <div key={i} className="w-0.5 h-0.5 rounded-full bg-slate-300" />
            ))}
          </div>
        </div>

        {/* Right: Live Analysis */}
        <div className="flex flex-col min-h-0 min-w-0 flex-1">
          <PanelErrorBoundary>
            <AnalysisPanel />
          </PanelErrorBoundary>
        </div>
      </div>

      {/* Start Meeting Modal */}
      {showModal && (
        <StartMeetingModal
          onConfirm={(customerId, meetingType, meetingName, participants, selectedRoles) =>
            startMeeting(customerId, meetingType, meetingName, participants, selectedRoles)
          }
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
