import { useState, useMemo } from "react";
import { useMeetingStore } from "../store/meetingStore";
import type { ParticipantInfo, SpeakerMappings } from "../types";

const BACKEND = "http://localhost:8000";

/** Compute word-count per speaker from transcript chunks */
function useTalkTime(): Record<string, number> {
  const chunks = useMeetingStore((s) => s.transcriptChunks);
  return useMemo(() => {
    const counts: Record<string, number> = {};
    for (const chunk of chunks) {
      const key = chunk.speaker ?? "__unknown__";
      const words = chunk.text.trim().split(/\s+/).filter(Boolean).length;
      counts[key] = (counts[key] ?? 0) + words;
    }
    return counts;
  }, [chunks]);
}

/** Readable speaker label before mapping */
function speakerLabel(id: string): string {
  const m = id.match(/(\d+)$/);
  if (m) return `Speaker ${parseInt(m[1]) + 1}`;
  return id;
}

const SPEAKER_COLORS = [
  "bg-emerald-500",
  "bg-violet-500",
  "bg-cyan-500",
  "bg-pink-500",
  "bg-orange-500",
];
function barColor(speakerId: string): string {
  const m = speakerId.match(/(\d+)$/);
  const idx = m ? parseInt(m[1]) % SPEAKER_COLORS.length : 0;
  return SPEAKER_COLORS[idx];
}

export function SpeakerMappingPanel() {
  const talkTime = useTalkTime();
  const participants = useMeetingStore((s) => s.participants);
  const speakerMappings = useMeetingStore((s) => s.speakerMappings);
  const setSpeakerMappings = useMeetingStore((s) => s.setSpeakerMappings);
  const meetingStatus = useMeetingStore((s) => s.meetingStatus);

  // Local editable state for the mapping table (speaker id -> draft info)
  const [draft, setDraft] = useState<SpeakerMappings>(() => ({ ...speakerMappings }));
  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<number | null>(null);

  // All speaker IDs seen in transcript
  const speakerIds = useMemo(() => {
    return Object.keys(talkTime).filter((k) => k !== "__unknown__").sort();
  }, [talkTime]);

  const totalWords = Object.values(talkTime).reduce((a, b) => a + b, 0);

  function setDraftField(speakerId: string, field: keyof ParticipantInfo, value: string) {
    setDraft((prev) => ({
      ...prev,
      [speakerId]: {
        ...(prev[speakerId] ?? { name: "", org: "", role: "" }),
        [field]: value,
      },
    }));
  }

  async function applyMapping() {
    setSaving(true);
    try {
      const res = await fetch(`${BACKEND}/meeting/speaker-mapping`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mappings: draft }),
      });
      if (res.ok) {
        setSpeakerMappings(draft);
        setLastSaved(Date.now());
      }
    } finally {
      setSaving(false);
    }
  }

  if (speakerIds.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-4 text-slate-500 text-sm gap-2">
        <svg className="w-8 h-8 text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
        <p>Speaker diarization data will appear here once the transcript starts.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto px-3 py-3 space-y-4">
      {/* Talk-time bars */}
      <div>
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Talk Time</p>
        <div className="space-y-2">
          {speakerIds.map((sid) => {
            const words = talkTime[sid] ?? 0;
            const pct = totalWords > 0 ? (words / totalWords) * 100 : 0;
            const info = speakerMappings[sid];
            const label = info?.name || speakerLabel(sid);
            return (
              <div key={sid} className="flex items-center gap-2">
                <span className="text-xs text-slate-400 w-24 shrink-0 truncate">{label}</span>
                <div className="flex-1 bg-slate-700 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full transition-all ${barColor(sid)}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-xs text-slate-500 w-10 text-right shrink-0">
                  {pct.toFixed(0)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Mapping table */}
      <div>
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Speaker Mapping</p>
        <div className="space-y-3">
          {speakerIds.map((sid) => {
            const info = draft[sid] ?? { name: "", org: "", role: "" };
            return (
              <div key={sid} className="bg-slate-900/50 border border-slate-700 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <div className={`w-2 h-2 rounded-full ${barColor(sid)}`} />
                  <span className="text-xs font-medium text-slate-300">{speakerLabel(sid)}</span>
                  {talkTime[sid] && (
                    <span className="text-xs text-slate-500">{talkTime[sid]} words</span>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-2">
                  {/* Name — autofill from participants list */}
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Name</label>
                    {participants.length > 0 ? (
                      <select
                        value={info.name}
                        onChange={(e) => {
                          const val = e.target.value;
                          setDraftField(sid, "name", val);
                          // Auto-fill org from participant entry if it has parenthetical
                          if (val && !info.org) {
                            const m = val.match(/\(([^)]+)\)/);
                            if (m) setDraftField(sid, "org", m[1]);
                          }
                        }}
                        className="w-full bg-slate-700 border border-slate-600 text-slate-100 text-xs rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      >
                        <option value="">— select —</option>
                        {participants.map((p) => (
                          <option key={p} value={p}>{p}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="text"
                        value={info.name}
                        onChange={(e) => setDraftField(sid, "name", e.target.value)}
                        placeholder="Full name"
                        className="w-full bg-slate-700 border border-slate-600 text-slate-100 text-xs rounded px-2 py-1.5 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    )}
                  </div>

                  {/* Org */}
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Organization</label>
                    <input
                      type="text"
                      value={info.org}
                      onChange={(e) => setDraftField(sid, "org", e.target.value)}
                      placeholder="e.g. AWS, Acme"
                      className="w-full bg-slate-700 border border-slate-600 text-slate-100 text-xs rounded px-2 py-1.5 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>

                  {/* Role */}
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Role</label>
                    <input
                      type="text"
                      value={info.role}
                      onChange={(e) => setDraftField(sid, "role", e.target.value)}
                      placeholder="e.g. Account SA"
                      className="w-full bg-slate-700 border border-slate-600 text-slate-100 text-xs rounded px-2 py-1.5 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Apply button */}
      <div className="flex items-center gap-3 pb-2">
        <button
          onClick={applyMapping}
          disabled={saving || meetingStatus !== "recording"}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium rounded-lg transition-colors"
        >
          {saving ? (
            <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          )}
          Apply Mapping & Re-analyze
        </button>
        {lastSaved && (
          <span className="text-xs text-emerald-400">
            Applied {new Date(lastSaved).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
        )}
      </div>

      {meetingStatus !== "recording" && (
        <p className="text-xs text-slate-500 text-center pb-2">
          Mapping can only be applied during an active meeting.
        </p>
      )}
    </div>
  );
}
