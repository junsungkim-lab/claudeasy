import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { wsUrl } from "@/api/client";

export function useRunWs(runId: number | null, boardId: number | null) {
  const qc = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;

    const connect = () => {
      const ws = new WebSocket(wsUrl(`/ws/run/${runId}`));
      wsRef.current = ws;

      ws.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data);

          // 카드 상태가 바뀔 때마다 runs 쿼리 갱신 (카드가 runs에 포함됨)
          // 서버가 보내는 실제 이벤트 타입: card_update, run_ready, run_done 등
          if (
            ev.type === "card_update" ||
            ev.type === "card_done" ||
            ev.type === "card_error" ||
            ev.type === "card_reset" ||
            ev.type === "run_ready" ||
            ev.type === "run_state"
          ) {
            qc.invalidateQueries({ queryKey: ["runs", boardId] });
          }

          // Run 완료
          if (ev.type === "run_done" || ev.type === "run_error") {
            qc.invalidateQueries({ queryKey: ["runs", boardId] });
            qc.invalidateQueries({ queryKey: ["boards"] });
            qc.invalidateQueries({ queryKey: ["sessions"] });
          }
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
  }, [runId, boardId, qc]);
}
