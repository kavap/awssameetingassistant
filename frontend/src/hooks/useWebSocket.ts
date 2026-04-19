import { useEffect, useRef } from "react";
import type { AnalysisResult, CCMState, RecommendationCard, WsMessage } from "../types";
import { useMeetingStore } from "../store/meetingStore";

const WS_URL = "ws://localhost:8000/ws";
const MAX_RETRIES = 5;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef(false);
  const generationRef = useRef(0);

  const {
    appendFinalChunk,
    setPartialText,
    prependRecommendation,
    setCCMState,
    setAnalysisTrackA,
    setAnalysisTrackB,
    setConnectionStatus,
    setMeetingStatus,
  } = useMeetingStore();

  useEffect(() => {
    function connect() {
      intentionalCloseRef.current = false;
      const generation = ++generationRef.current;
      setConnectionStatus("connecting");
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        retriesRef.current = 0;
        setConnectionStatus("connected");
      };

      ws.onmessage = (event) => {
        let msg: WsMessage;
        try {
          msg = JSON.parse(event.data);
        } catch {
          return;
        }

        // Debug: log every message type (suppress high-frequency transcript partials)
        if (msg.type !== "transcript_partial") {
          console.debug(`[WS recv] type=${msg.type} ts=${msg.ts}`);
        }

        try {
        switch (msg.type) {
          case "transcript_partial": {
            const p = msg.payload as { text: string };
            setPartialText(p.text);
            break;
          }
          case "transcript_final": {
            const p = msg.payload as { text: string; speaker: string | null };
            appendFinalChunk(p.text, p.speaker, msg.ts);
            break;
          }
          case "recommendation": {
            const card = {
              ...(msg.payload as RecommendationCard),
              timestamp: msg.ts,
            };
            prependRecommendation(card);
            break;
          }
          case "ccm_update": {
            setCCMState(msg.payload as CCMState);
            break;
          }
          case "analysis_update": {
            const ar = msg.payload as AnalysisResult;
            console.log(
              `[WS analysis_update] stage=${ar.stage} cycle=${ar.cycle_count} ` +
              `situation_len=${ar.situation?.length ?? 0} ` +
              `current_state_len=${ar.current_state?.length ?? 0} ` +
              `customer_needs_len=${ar.customer_needs?.length ?? 0} ` +
              `sources=${ar.sources?.length ?? 0}`,
              ar
            );
            console.log("[WS analysis_update] calling setAnalysisTrackA...");
            setAnalysisTrackA(ar);
            console.log("[WS analysis_update] setAnalysisTrackA done");
            break;
          }
          case "steered_analysis_update": {
            const arB = msg.payload as AnalysisResult;
            console.log(`[WS steered_analysis_update] stage=${arB.stage} cycle=${arB.cycle_count}`, arB);
            setAnalysisTrackB(arB);
            break;
          }
          case "meeting_started": {
            setMeetingStatus("recording");
            break;
          }
          case "meeting_stopped": {
            setMeetingStatus("stopped");
            break;
          }
          case "error": {
            console.error("Backend error:", msg.payload);
            break;
          }
        }
        } catch (e) {
          console.error("WS message handling error:", e, "msg:", msg);
        }
      };

      ws.onclose = () => {
        // Ignore stale close events from connections superseded by cleanup+remount
        if (generationRef.current !== generation) return;
        setConnectionStatus("disconnected");
        wsRef.current = null;

        if (!intentionalCloseRef.current && retriesRef.current < MAX_RETRIES) {
          const delay = Math.min(500 * 2 ** retriesRef.current, 8000);
          retriesRef.current++;
          retryTimerRef.current = setTimeout(connect, delay);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      intentionalCloseRef.current = true;
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      wsRef.current?.close();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function sendMessage(data: unknown) {
    wsRef.current?.send(JSON.stringify(data));
  }

  return { sendMessage };
}
