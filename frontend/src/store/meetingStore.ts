import { create } from "zustand";
import type {
  AnalysisResult,
  CCMState,
  ConnectionStatus,
  MeetingStatus,
  RecommendationCard,
  TranscriptChunk,
} from "../types";

let _chunkCounter = 0;

interface MeetingStore {
  transcriptChunks: TranscriptChunk[];
  partialText: string;
  recommendations: RecommendationCard[];
  ccmState: CCMState | null;
  analysisTrackA: AnalysisResult | null;
  analysisTrackB: AnalysisResult | null;
  connectionStatus: ConnectionStatus;
  meetingStatus: MeetingStatus;

  appendFinalChunk: (text: string, speaker: string | null, ts: number) => void;
  setPartialText: (text: string) => void;
  prependRecommendation: (card: RecommendationCard) => void;
  dismissRecommendation: (id: string) => void;
  setCCMState: (state: CCMState) => void;
  setAnalysisTrackA: (result: AnalysisResult) => void;
  setAnalysisTrackB: (result: AnalysisResult) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  setMeetingStatus: (status: MeetingStatus) => void;
  reset: () => void;
}

export const useMeetingStore = create<MeetingStore>((set) => ({
  transcriptChunks: [],
  partialText: "",
  recommendations: [],
  ccmState: null,
  analysisTrackA: null,
  analysisTrackB: null,
  connectionStatus: "disconnected",
  meetingStatus: "idle",

  appendFinalChunk: (text, speaker, ts) =>
    set((state) => {
      const chunk: TranscriptChunk = {
        id: String(++_chunkCounter),
        text,
        speaker,
        timestamp: ts,
        isPartial: false,
      };
      const chunks = [...state.transcriptChunks, chunk];
      // Keep last 200 final chunks
      return {
        transcriptChunks: chunks.length > 200 ? chunks.slice(-200) : chunks,
        partialText: "",
      };
    }),

  setPartialText: (text) => set({ partialText: text }),

  prependRecommendation: (card) =>
    set((state) => {
      const recs = [card, ...state.recommendations];
      return { recommendations: recs.length > 20 ? recs.slice(0, 20) : recs };
    }),

  dismissRecommendation: (id) =>
    set((state) => ({
      recommendations: state.recommendations.filter((r) => r.id !== id),
    })),

  setCCMState: (ccmState) => set({ ccmState }),

  setAnalysisTrackA: (result) => set({ analysisTrackA: result }),

  setAnalysisTrackB: (result) => set({ analysisTrackB: result }),

  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),

  setMeetingStatus: (meetingStatus) => set({ meetingStatus }),

  reset: () =>
    set({
      transcriptChunks: [],
      partialText: "",
      recommendations: [],
      ccmState: null,
      analysisTrackA: null,
      analysisTrackB: null,
      meetingStatus: "idle",
    }),
}));
