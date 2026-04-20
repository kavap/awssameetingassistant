import { useState, useEffect, useCallback } from "react";
import type { MeetingIndexEntry, SavedMeeting, TranscriptChunk } from "../types";
import { AnalysisView } from "./AnalysisView";
import { DiagramView, DIAGRAM_TAB_CONFIG, type DiagramTab } from "./MermaidRender";

const BACKEND = "http://localhost:8000";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(ts: number): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

function formatTime(ts: number): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleTimeString("en-US", {
    hour: "2-digit", minute: "2-digit",
  });
}

function formatDuration(start: number, end: number): string {
  if (!start || !end || end <= start) return "";
  const secs = Math.floor(end - start);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatSpeaker(speaker: string | null, mapping?: Record<string, { name: string }>): string {
  if (!speaker) return "—";
  if (mapping?.[speaker]?.name) {
    const parts = mapping[speaker].name.split(/\s+/);
    return parts.length > 1 ? `${parts[0]} ${parts[1][0]}.` : parts[0];
  }
  const m = speaker.match(/spk_(\d+)/i) ?? speaker.match(/(\d+)$/);
  if (m) return `Spk ${parseInt(m[1], 10) + 1}`;
  return speaker;
}

function speakerColor(speaker: string | null): string {
  if (!speaker) return "text-slate-500";
  const m = speaker.match(/spk_(\d+)/i);
  const colors = ["text-blue-400", "text-emerald-400", "text-amber-400", "text-violet-400", "text-pink-400"];
  if (m) return colors[parseInt(m[1], 10) % colors.length];
  return "text-slate-400";
}

function stageBadge(stage: number) {
  if (stage === 3) return { label: "Stage 3", cls: "text-emerald-400 bg-emerald-900/30 border-emerald-700" };
  if (stage === 2) return { label: "Stage 2", cls: "text-blue-400 bg-blue-900/30 border-blue-700" };
  return { label: "Stage 1", cls: "text-yellow-400 bg-yellow-900/30 border-yellow-700" };
}

// ---------------------------------------------------------------------------
// MeetingDetail — full saved meeting viewer
// ---------------------------------------------------------------------------

type DetailTab = "transcript" | "analysis" | "diagrams";
type AnalysisSubTab = "auto" | "steered";

function MeetingDetail({ meeting, onBack }: { meeting: SavedMeeting; onBack: () => void }) {
  const [activeTab, setActiveTab] = useState<DetailTab>("transcript");
  const [analysisSubTab, setAnalysisSubTab] = useState<AnalysisSubTab>("auto");
  const [activeDiagram, setActiveDiagram] = useState<DiagramTab>("current");

  const hasDiagrams = !!(
    meeting.analysis_track_a?.current_state_diagram ||
    meeting.analysis_track_a?.mermaid_diagram ||
    meeting.analysis_track_b?.mermaid_diagram
  );

  const diagramSources: Record<DiagramTab, string | undefined> = {
    current: meeting.analysis_track_a?.current_state_diagram,
    auto:    meeting.analysis_track_a?.mermaid_diagram,
    steered: meeting.analysis_track_b?.mermaid_diagram,
  };

  const diagramHasContent: Record<DiagramTab, boolean> = {
    current: !!meeting.analysis_track_a?.current_state_diagram,
    auto:    !!meeting.analysis_track_a?.mermaid_diagram,
    steered: !!meeting.analysis_track_b?.mermaid_diagram,
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Detail header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 shrink-0">
        <button
          onClick={onBack}
          className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200 transition-colors"
          title="Back to list"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold text-slate-200 truncate">
            {meeting.meeting_name || meeting.meeting_type}
          </div>
          {meeting.meeting_name && (
            <div className="text-[10px] text-slate-500">{meeting.meeting_type}</div>
          )}
          <div className="text-[10px] text-slate-500 flex items-center gap-2">
            <span>{meeting.customer_id !== "anonymous" ? meeting.customer_id : "Anonymous"}</span>
            <span>·</span>
            <span>{formatDate(meeting.started_at)} {formatTime(meeting.started_at)}</span>
            {meeting.stopped_at > meeting.started_at && (
              <>
                <span>·</span>
                <span>{formatDuration(meeting.started_at, meeting.stopped_at)}</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-0 border-b border-slate-700 shrink-0 px-2">
        {(["transcript", "analysis", "diagrams"] as DetailTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors capitalize ${
              activeTab === tab
                ? tab === "transcript" ? "border-blue-500 text-slate-100"
                  : tab === "analysis" ? "border-violet-500 text-slate-100"
                  : "border-emerald-500 text-slate-100"
                : "border-transparent text-slate-500 hover:text-slate-300"
            }`}
          >
            {tab}
            {tab === "diagrams" && hasDiagrams && (
              <span className="ml-1 w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0 flex flex-col">
        {activeTab === "transcript" && (
          <TranscriptView chunks={meeting.transcript} speakerMapping={meeting.speaker_mapping ?? {}} />
        )}

        {activeTab === "analysis" && (
          <div className="flex flex-col flex-1 min-h-0">
            {/* Sub-tabs */}
            <div className="flex items-center gap-0 px-2 border-b border-slate-700/50 shrink-0">
              <button
                onClick={() => setAnalysisSubTab("auto")}
                className={`px-3 py-1.5 text-xs border-b-2 -mb-px transition-colors ${
                  analysisSubTab === "auto"
                    ? "border-blue-500 text-slate-200"
                    : "border-transparent text-slate-500 hover:text-slate-300"
                }`}
              >
                Auto
              </button>
              <button
                onClick={() => setAnalysisSubTab("steered")}
                className={`px-3 py-1.5 text-xs border-b-2 -mb-px transition-colors ${
                  analysisSubTab === "steered"
                    ? "border-violet-500 text-slate-200"
                    : "border-transparent text-slate-500 hover:text-slate-300"
                }`}
              >
                Steered
                {meeting.analysis_track_b && <span className="ml-1 w-1.5 h-1.5 rounded-full bg-violet-400 inline-block" />}
              </button>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2">
              {analysisSubTab === "auto" ? (
                meeting.analysis_track_a ? (
                  <AnalysisView result={meeting.analysis_track_a} />
                ) : (
                  <p className="text-xs text-slate-500 mt-4 text-center">No auto analysis recorded.</p>
                )
              ) : (
                meeting.analysis_track_b ? (
                  <AnalysisView result={meeting.analysis_track_b} />
                ) : (
                  <p className="text-xs text-slate-500 mt-4 text-center">No steered analysis recorded.</p>
                )
              )}
            </div>
          </div>
        )}

        {activeTab === "diagrams" && (
          <div className="flex flex-col flex-1 min-h-0">
            {/* Diagram tab bar */}
            <div className="flex items-center gap-1 px-2 pt-2 pb-0 border-b border-slate-700 shrink-0">
              {(["current", "auto", "steered"] as DiagramTab[]).map((tab) => {
                const cfg = DIAGRAM_TAB_CONFIG[tab];
                const isActive = activeDiagram === tab;
                return (
                  <button
                    key={tab}
                    onClick={() => setActiveDiagram(tab)}
                    className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded-t border-b-2 transition-colors ${
                      isActive ? cfg.activeClass : "text-slate-500 hover:text-slate-300 border-transparent"
                    }`}
                  >
                    <span className="font-medium">{cfg.label}</span>
                    <span className={`text-[10px] ${isActive ? "opacity-70" : "opacity-50"}`}>{cfg.sublabel}</span>
                    {diagramHasContent[tab] && (
                      <span className={`w-1.5 h-1.5 rounded-full ml-0.5 ${
                        tab === "steered" ? "bg-violet-400" : tab === "auto" ? "bg-blue-400" : "bg-slate-400"
                      }`} />
                    )}
                  </button>
                );
              })}
            </div>
            <DiagramView
              source={diagramSources[activeDiagram]}
              tab={activeDiagram}
              hasContent={diagramHasContent[activeDiagram]}
              emptyMessage="Not recorded for this meeting."
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TranscriptView — read-only transcript for saved meetings
// ---------------------------------------------------------------------------

function TranscriptView({
  chunks,
  speakerMapping = {},
}: {
  chunks: TranscriptChunk[];
  speakerMapping?: Record<string, { name: string; org: string; role: string }>;
}) {
  if (!chunks.length) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-xs text-slate-500">No transcript recorded.</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
      {chunks.map((chunk) => (
        <div key={chunk.id} className="flex gap-2 text-xs">
          <span className="text-slate-600 shrink-0 w-14 text-right tabular-nums">
            {formatTime(chunk.timestamp)}
          </span>
          <span
            className={`shrink-0 w-14 font-medium truncate ${speakerColor(chunk.speaker)}`}
            title={speakerMapping[chunk.speaker ?? ""]?.name ?? chunk.speaker ?? undefined}
          >
            {formatSpeaker(chunk.speaker, speakerMapping)}
          </span>
          <span className="text-slate-300 leading-relaxed">{chunk.text}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// MeetingListItem
// ---------------------------------------------------------------------------

function MeetingListItem({
  entry,
  onSelect,
  onDelete,
}: {
  entry: MeetingIndexEntry;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const badge = stageBadge(entry.stage);

  function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    if (confirmDelete) {
      onDelete();
    } else {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
    }
  }

  return (
    <button
      onClick={onSelect}
      className="w-full text-left px-3 py-2.5 hover:bg-slate-800 transition-colors border-b border-slate-800 group"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-xs font-medium text-slate-200 truncate">
              {entry.meeting_name || entry.meeting_type}
            </span>
            {entry.stage > 0 && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${badge.cls} shrink-0`}>
                {badge.label}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-[10px] text-slate-500">
            {entry.customer_id !== "anonymous" && (
              <>
                <span className="text-slate-400">{entry.customer_id}</span>
                <span>·</span>
              </>
            )}
            <span>{formatDate(entry.started_at)}</span>
            <span>·</span>
            <span>{formatTime(entry.started_at)}</span>
            {entry.stopped_at > entry.started_at && (
              <>
                <span>·</span>
                <span>{formatDuration(entry.started_at, entry.stopped_at)}</span>
              </>
            )}
          </div>
          <div className="text-[10px] text-slate-600 mt-0.5">
            {entry.transcript_count} segments
            {entry.cycle_count > 0 && ` · ${entry.cycle_count} analysis cycles`}
          </div>
        </div>
        <button
          onClick={handleDelete}
          className={`shrink-0 text-[10px] px-2 py-0.5 rounded transition-colors opacity-0 group-hover:opacity-100 ${
            confirmDelete
              ? "bg-red-900/60 text-red-300 border border-red-700"
              : "bg-slate-700 text-slate-400 hover:bg-red-900/40 hover:text-red-400"
          }`}
          title="Delete meeting"
        >
          {confirmDelete ? "Confirm" : "Delete"}
        </button>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// PastMeetingsDrawer — main export
// ---------------------------------------------------------------------------

export function PastMeetingsDrawer({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [meetings, setMeetings] = useState<MeetingIndexEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedMeeting, setSelectedMeeting] = useState<SavedMeeting | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const fetchList = useCallback(() => {
    setLoading(true);
    setError(null);
    fetch(`${BACKEND}/meetings`)
      .then((r) => r.json())
      .then((data) => setMeetings(data.meetings ?? []))
      .catch(() => setError("Failed to load meetings."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (open) {
      setSelectedMeeting(null);
      fetchList();
    }
  }, [open, fetchList]);

  function selectMeeting(sessionId: string) {
    setLoadingDetail(true);
    fetch(`${BACKEND}/meetings/${sessionId}`)
      .then((r) => r.json())
      .then((data) => setSelectedMeeting(data))
      .catch(() => setError("Failed to load meeting details."))
      .finally(() => setLoadingDetail(false));
  }

  async function deleteMeeting(sessionId: string) {
    await fetch(`${BACKEND}/meetings/${sessionId}`, { method: "DELETE" });
    setMeetings((prev) => prev.filter((m) => m.session_id !== sessionId));
  }

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div className="fixed right-0 top-0 h-full w-[600px] max-w-[90vw] bg-slate-900 border-l border-slate-700 z-50 flex flex-col shadow-2xl">
        {selectedMeeting ? (
          /* Detail view */
          loadingDetail ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-xs text-slate-500 animate-pulse">Loading...</div>
            </div>
          ) : (
            <MeetingDetail
              meeting={selectedMeeting}
              onBack={() => setSelectedMeeting(null)}
            />
          )
        ) : (
          /* List view */
          <>
            {/* List header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 shrink-0">
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                </svg>
                <span className="text-sm font-semibold text-slate-200">Past Meetings</span>
                {meetings.length > 0 && (
                  <span className="text-[10px] text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded">
                    {meetings.length}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={fetchList}
                  className="p-1.5 hover:bg-slate-800 rounded text-slate-500 hover:text-slate-300 transition-colors"
                  title="Refresh"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 hover:bg-slate-800 rounded text-slate-500 hover:text-slate-300 transition-colors"
                  title="Close"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* List body */}
            <div className="flex-1 min-h-0 overflow-y-auto">
              {loading && (
                <div className="flex items-center justify-center py-12">
                  <div className="text-xs text-slate-500 animate-pulse">Loading meetings...</div>
                </div>
              )}
              {error && (
                <div className="px-4 py-3 text-xs text-red-400 bg-red-950/30 border-b border-red-900/50">
                  {error}
                </div>
              )}
              {!loading && !error && meetings.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
                  <div className="w-12 h-12 bg-slate-800 rounded-full flex items-center justify-center mb-4">
                    <svg className="w-6 h-6 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                        d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                    </svg>
                  </div>
                  <p className="text-sm text-slate-500 font-medium">No meetings saved yet</p>
                  <p className="text-xs text-slate-600 mt-1">Meetings are saved automatically when you stop recording.</p>
                </div>
              )}
              {!loading && meetings.map((entry) => (
                <MeetingListItem
                  key={entry.session_id}
                  entry={entry}
                  onSelect={() => selectMeeting(entry.session_id)}
                  onDelete={() => deleteMeeting(entry.session_id)}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );
}
