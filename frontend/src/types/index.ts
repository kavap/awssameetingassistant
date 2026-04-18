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

export type WsMessageType =
  | "transcript_partial"
  | "transcript_final"
  | "recommendation"
  | "ccm_update"
  | "meeting_started"
  | "meeting_stopped"
  | "error";

export interface WsMessage {
  type: WsMessageType;
  ts: number;
  payload: unknown;
}

export type MeetingStatus = "idle" | "recording" | "stopped";
export type ConnectionStatus = "connecting" | "connected" | "disconnected";
