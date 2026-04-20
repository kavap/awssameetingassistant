export interface TranscriptChunk {
  id: string;
  text: string;
  speaker: string | null;
  timestamp: number;
  isPartial: boolean;
}

export interface RecommendationCard {
  id: string;
  title: string;
  summary: string;
  service_mentioned: string[];
  action_items: string[];
  source_urls: string[];
  confidence: number;
  trigger: string;
  timestamp: number;
  dismissed?: boolean;
}

export interface MentionedService {
  name: string;
  category: "aws" | "competitor" | "generic";
  mention_count: number;
}

export interface Topic {
  name: string;
  keywords: string[];
  confidence: number;
}

export interface OpenQuestion {
  id: string;
  text: string;
  raised_at: number;
  resolved: boolean;
}

export interface CCMState {
  session_id: string;
  meeting_goal: string;
  active_topics: Topic[];
  open_questions: OpenQuestion[];
  mentioned_services: Record<string, MentionedService>;
  last_updated_at: number;
}

export type AnalysisStage = 1 | 2 | 3;

export interface AnalysisResult {
  id: string;
  stage: AnalysisStage;
  ready: boolean;
  reasoning: string;
  situation: string;
  current_state: string;
  customer_needs: string;
  open_questions: string;
  proposed_architecture: string;
  key_recommendations: string;
  sources: string[];
  current_state_diagram: string;
  mermaid_diagram: string;
  action_items?: { aws: string[]; partner: string[]; customer: string[] };
  cycle_count: number;
  segment_count?: number;
  is_steered: boolean;
  timestamp: number;
}

export const MEETING_TYPES = [
  "Customer Meeting",
  "OneTeam / Partner Meeting",
  "SA Manager Sync",
  "Internal Architecture Review",
  "Competitive Deal",
  "Migration Assessment",
  "GenAI / ML Workshop",
  "Cost Optimization Review",
] as const;

export type MeetingType = typeof MEETING_TYPES[number];

export interface ParticipantInfo {
  name: string;
  org: string;
  role: string;
}

export type SpeakerMappings = Record<string, ParticipantInfo>;

export type WsMessageType =
  | "transcript_partial"
  | "transcript_final"
  | "recommendation"
  | "ccm_update"
  | "analysis_update"
  | "steered_analysis_update"
  | "meeting_started"
  | "meeting_stopped"
  | "speaker_mapping_update"
  | "error";

export interface WsMessage {
  type: WsMessageType;
  ts: number;
  payload: unknown;
}

export type MeetingStatus = "idle" | "recording" | "stopped";
export type ConnectionStatus = "connecting" | "connected" | "disconnected";

export interface MeetingIndexEntry {
  session_id: string;
  customer_id: string;
  meeting_type: string;
  meeting_name: string;
  started_at: number;
  stopped_at: number;
  transcript_count: number;
  stage: number;
  cycle_count: number;
}

export interface SavedMeeting {
  session_id: string;
  customer_id: string;
  meeting_type: string;
  meeting_name: string;
  started_at: number;
  stopped_at: number;
  transcript: TranscriptChunk[];
  analysis_track_a: AnalysisResult | null;
  analysis_track_b: AnalysisResult | null;
  recommendations: RecommendationCard[];
  participants: string[];
  selected_roles: string[];
  speaker_mapping: SpeakerMappings;
}
