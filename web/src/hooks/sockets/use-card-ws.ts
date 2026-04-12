import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { wsUrl } from "@/api/client";

export function useCardWs(cardId: number | null, initialOutput: string | null) {
  const [output, setOutput] = useState(initialOutput ?? "");
  const [streaming, setStreaming] = useState(false);
  const [feedbackSeq, setFeedbackSeq] = useState(0); // 피드백 갱신 시그널
  const qc = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    setOutput(initialOutput ?? "");
  }, [initialOutput]);

  useEffect(() => {
    if (!cardId) return;

    const ws = new WebSocket(wsUrl(`/ws/card/${cardId}`));
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data);
        if (ev.type === "init" && ev.buffer) {
          setOutput(ev.buffer);
        } else if (ev.type === "chunk") {
          setStreaming(true);
          setOutput((prev) => prev + ev.text);
        } else if (ev.type === "card_done" || ev.type === "card_error") {
          setStreaming(false);
        } else if (ev.type === "card_reset") {
          setOutput("");
          setStreaming(false);
        } else if (ev.type === "feedback_update") {
          // 에이전트 답변 도착 — feedback 쿼리 즉시 갱신
          qc.invalidateQueries({ queryKey: ["feedback", cardId] });
          setFeedbackSeq((s) => s + 1);
        } else if (ev.type === "slides_ready") {
          // 인스타 슬라이드 생성 완료 — slides 쿼리 갱신
          qc.invalidateQueries({ queryKey: ["slides", cardId] });
        }
      } catch {}
    };

    ws.onclose = () => setStreaming(false);
    ws.onerror = () => ws.close();

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [cardId, qc]);

  return { output, streaming, feedbackSeq };
}
