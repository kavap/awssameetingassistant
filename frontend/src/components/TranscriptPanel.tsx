import { useEffect, useRef, useState, useMemo } from "react";
import { useMeetingStore } from "../store/meetingStore";
import { TranscriptChunkItem } from "./TranscriptChunkItem";

const BACKEND = "http://localhost:8000";

export function TranscriptPanel() {
  const transcriptChunks = useMeetingStore((s) => s.transcriptChunks);
  const partialText = useMeetingStore((s) => s.partialText);
  const speakerMappings = useMeetingStore((s) => s.speakerMappings);
  const flushPendingCorrections = useMeetingStore((s) => s.flushPendingCorrections);
  const meetingStatus = useMeetingStore((s) => s.meetingStatus);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [speakerFilter, setSpeakerFilter] = useState<string>("all");
  const prevChunkCount = useRef(transcriptChunks.length);

  // Collect all distinct speakers for the filter dropdown
  const speakerIds = useMemo(() => {
    const seen = new Set<string>();
    for (const chunk of transcriptChunks) {
      if (chunk.speaker) seen.add(chunk.speaker);
    }
    return [...seen].sort();
  }, [transcriptChunks]);

  // Flush pending speaker corrections to backend when new transcript arrives
  useEffect(() => {
    if (
      meetingStatus !== "recording" ||
      transcriptChunks.length <= prevChunkCount.current
    ) {
      prevChunkCount.current = transcriptChunks.length;
      return;
    }
    prevChunkCount.current = transcriptChunks.length;

    const corrections = flushPendingCorrections();
    const entries = Object.entries(corrections);
    if (entries.length === 0) return;

    // Build index-based corrections for backend
    // Map chunkId → position in transcriptChunks array
    const indexCorrections = entries.map(([chunkId, speakerId]) => {
      const idx = transcriptChunks.findIndex((c) => c.id === chunkId);
      return idx >= 0 ? { index: idx, speaker_id: speakerId } : null;
    }).filter(Boolean);

    if (indexCorrections.length > 0) {
      fetch(`${BACKEND}/transcript/speaker-corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corrections: indexCorrections }),
      }).catch((e) => console.warn("[TranscriptPanel] Failed to flush corrections:", e));
    }
  }, [transcriptChunks.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll to bottom on new content (only when not filtering)
  useEffect(() => {
    if (speakerFilter === "all") {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [transcriptChunks.length, partialText, speakerFilter]);

  const filtered = speakerFilter === "all"
    ? transcriptChunks
    : transcriptChunks.filter((c) => c.speaker === speakerFilter);

  function speakerDisplayName(id: string): string {
    const info = speakerMappings[id];
    if (info?.name) return info.name;
    const m = id.match(/(\d+)$/);
    return `Speaker ${m ? parseInt(m[1]) + 1 : id}`;
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-slate-700 flex items-center gap-2 shrink-0">
        <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
          Live Transcript
        </span>

        {/* Speaker filter */}
        {speakerIds.length > 1 && (
          <select
            value={speakerFilter}
            onChange={(e) => setSpeakerFilter(e.target.value)}
            className="ml-2 bg-slate-800 border border-slate-600 text-slate-300 text-xs rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="all">All speakers</option>
            {speakerIds.map((id) => (
              <option key={id} value={id}>{speakerDisplayName(id)}</option>
            ))}
          </select>
        )}

        <span className="ml-auto text-xs text-slate-600">
          {filtered.length}{speakerFilter !== "all" ? `/${transcriptChunks.length}` : ""} segments
        </span>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {filtered.length === 0 && !partialText && (
          <div className="flex flex-col items-center justify-center h-full text-slate-600 text-sm gap-2">
            {speakerFilter !== "all" ? (
              <>
                <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                <span>No segments for this speaker yet.</span>
              </>
            ) : (
              <>
                <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
                <span>Waiting for audio...</span>
              </>
            )}
          </div>
        )}

        {filtered.map((chunk) => (
          <TranscriptChunkItem
            key={chunk.id}
            chunk={chunk}
            displayName={speakerMappings[chunk.speaker ?? ""]?.name}
            allSpeakerIds={speakerIds}
          />
        ))}

        {/* Partial text — show only when not filtering */}
        {speakerFilter === "all" && partialText && (
          <div className="flex gap-2 py-1 px-2 text-sm leading-relaxed">
            <span className="text-slate-500 tabular-nums text-xs pt-0.5 shrink-0 w-[4.5rem]" />
            <span className="text-slate-500 w-14 shrink-0" />
            <span className="text-slate-500 italic">{partialText}</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
