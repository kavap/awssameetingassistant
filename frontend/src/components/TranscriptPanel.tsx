import { useEffect, useRef } from "react";
import { useMeetingStore } from "../store/meetingStore";
import { TranscriptChunkItem } from "./TranscriptChunkItem";

export function TranscriptPanel() {
  const transcriptChunks = useMeetingStore((s) => s.transcriptChunks);
  const partialText = useMeetingStore((s) => s.partialText);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcriptChunks.length, partialText]);

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
        <span className="ml-auto text-xs text-slate-600">
          {transcriptChunks.length} segments
        </span>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {transcriptChunks.length === 0 && !partialText && (
          <div className="flex flex-col items-center justify-center h-full text-slate-600 text-sm gap-2">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
            <span>Waiting for audio...</span>
          </div>
        )}

        {/* Full transcript — all chunks, scroll to bottom */}
        {transcriptChunks.map((chunk) => (
          <TranscriptChunkItem key={chunk.id} chunk={chunk} />
        ))}

        {/* Partial / in-progress text */}
        {partialText && (
          <div className="flex gap-2 py-1 px-2 text-sm leading-relaxed">
            <span className="text-slate-500 tabular-nums text-xs pt-0.5 shrink-0 w-[4.5rem]" />
            <span className="text-slate-500 w-10 shrink-0" />
            <span className="text-slate-500 italic">{partialText}</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
