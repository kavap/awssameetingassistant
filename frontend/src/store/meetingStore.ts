import { create } from "zustand";
import type {
  AnalysisResult,
  CCMState,
  ConnectionStatus,
  MeetingStatus,
  ParticipantInfo,
  RecommendationCard,
  SpeakerMappings,
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

  // Session metadata — set from meeting_started WS event, used for save-on-stop
  sessionId: string | null;
  customerId: string;
  meetingType: string;
  meetingName: string;
  meetingStartedAt: number | null;

  // Participant + speaker mapping
  participants: string[];
  selectedRoles: string[];
  speakerMappings: SpeakerMappings;

  // Available roles list (fetched from config + custom) — shared across modal and mapping panel
  availableRoles: string[];
  // Role descriptions keyed by role name — used for tooltips and Sonnet context
  roleDescriptions: Record<string, string>;

  // Pending speaker corrections not yet flushed to backend (chunkId → newSpeakerId)
  pendingCorrections: Record<string, string>;

  appendFinalChunk: (text: string, speaker: string | null, ts: number) => void;
  setPartialText: (text: string) => void;
  prependRecommendation: (card: RecommendationCard) => void;
  dismissRecommendation: (id: string) => void;
  setCCMState: (state: CCMState) => void;
  setAnalysisTrackA: (result: AnalysisResult) => void;
  setAnalysisTrackB: (result: AnalysisResult) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  setMeetingStatus: (status: MeetingStatus) => void;
  setSessionMeta: (
    sessionId: string,
    customerId: string,
    meetingType: string,
    meetingName: string,
    participants: string[],
    selectedRoles: string[],
    startedAt: number,
  ) => void;
  setSpeakerMappings: (mappings: SpeakerMappings) => void;
  updateSpeakerMapping: (speakerId: string, info: ParticipantInfo) => void;
  setAvailableRoles: (roles: string[]) => void;
  setRoleDescriptions: (descriptions: Record<string, string>) => void;
  correctChunkSpeaker: (chunkId: string, newSpeakerId: string) => void;
  flushPendingCorrections: () => Record<string, string>;
  reset: () => void;
}

export const useMeetingStore = create<MeetingStore>((set, get) => ({
  transcriptChunks: [],
  partialText: "",
  recommendations: [],
  ccmState: null,
  analysisTrackA: null,
  analysisTrackB: null,
  connectionStatus: "disconnected",
  meetingStatus: "idle",
  sessionId: null,
  customerId: "anonymous",
  meetingType: "Customer Meeting",
  meetingName: "",
  meetingStartedAt: null,
  participants: [],
  selectedRoles: [],
  speakerMappings: {},
  availableRoles: [],
  roleDescriptions: {},
  pendingCorrections: {},

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
      return {
        transcriptChunks: chunks,
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

  setSessionMeta: (sessionId, customerId, meetingType, meetingName, participants, selectedRoles, startedAt) =>
    set({ sessionId, customerId, meetingType, meetingName, participants, selectedRoles, meetingStartedAt: startedAt }),

  setSpeakerMappings: (mappings) => set({ speakerMappings: mappings }),

  updateSpeakerMapping: (speakerId, info) =>
    set((state) => ({
      speakerMappings: { ...state.speakerMappings, [speakerId]: info },
    })),

  setAvailableRoles: (roles) => set({ availableRoles: roles }),

  setRoleDescriptions: (descriptions) => set({ roleDescriptions: descriptions }),

  correctChunkSpeaker: (chunkId, newSpeakerId) =>
    set((state) => ({
      transcriptChunks: state.transcriptChunks.map((c) =>
        c.id === chunkId ? { ...c, speaker: newSpeakerId } : c
      ),
      pendingCorrections: { ...state.pendingCorrections, [chunkId]: newSpeakerId },
    })),

  flushPendingCorrections: () => {
    const corrections = get().pendingCorrections;
    set({ pendingCorrections: {} });
    return corrections;
  },

  reset: () =>
    set({
      transcriptChunks: [],
      partialText: "",
      recommendations: [],
      ccmState: null,
      analysisTrackA: null,
      analysisTrackB: null,
      meetingStatus: "idle",
      sessionId: null,
      customerId: "anonymous",
      meetingType: "Customer Meeting",
      meetingName: "",
      meetingStartedAt: null,
      participants: [],
      selectedRoles: [],
      speakerMappings: {},
      availableRoles: [],
      roleDescriptions: {},
      pendingCorrections: {},
    }),
}));
