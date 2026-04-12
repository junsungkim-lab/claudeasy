import { useEffect, useRef, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { wsUrl } from "@/api/client";

export interface BoardEvent {
  type: string;
  text?: string;
  [key: string]: unknown;
}

export function useBoardWs(boardId: number | null) {
  const qc = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const [events, setEvents] = useState<BoardEvent[]>([]);
  const [statusText, setStatusText] = useState<string | null>(null);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setStatusText(null);
  }, []);

  useEffect(() => {
    if (!boardId) return;

    clearEvents();

    const connect = () => {
      const ws = new WebSocket(wsUrl(`/ws/board/${boardId}`));
      wsRef.current = ws;

      ws.onmessage = (e) => {
        try {
          const ev: BoardEvent = JSON.parse(e.data);

          // Status text (harness 단계 진행 상황)
          if (ev.type === "status" && ev.text) {
            setStatusText(ev.text);
            setEvents((prev) => [...prev.slice(-200), ev]);
          }

          // Harness 생성 chunk (Claude 스트리밍)
          if (ev.type === "harness_chunk" && ev.text) {
            setEvents((prev) => {
              const last = prev[prev.length - 1];
              if (last?.type === "harness_chunk") {
                return [
                  ...prev.slice(0, -1),
                  { ...last, text: (last.text ?? "") + ev.text },
                ];
              }
              return [...prev.slice(-200), ev];
            });
          }

          // 모든 이벤트에서 boards + runs 갱신 (상태 변화 즉시 반영)
          qc.invalidateQueries({ queryKey: ["boards"] });
          qc.invalidateQueries({ queryKey: ["runs", boardId] });

          if (ev.type === "board_ready") setStatusText(null);
        } catch {}
      };

      ws.onclose = () => {
        setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [boardId, qc, clearEvents]);

  return { events, statusText, clearEvents };
}
