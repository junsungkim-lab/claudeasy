import { useEffect, useRef, useState } from "react";
import { wsUrl } from "@/api/client";

export interface TrendingStructured {
  verdict: "recommended" | "risky" | "skip";
  score: number;
  why: string;
}

export function useTrendingWs(analyzeId: string | null) {
  const [output, setOutput] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [structured, setStructured] = useState<TrendingStructured | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!analyzeId) return;

    setOutput("");
    setDone(false);
    setError(null);
    setStructured(null);

    const ws = new WebSocket(wsUrl(`/ws/trending/${analyzeId}`));
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data);
        if (ev.type === "chunk") {
          setOutput((prev) => prev + ev.text);
        } else if (ev.type === "done") {
          if (ev.structured) setStructured(ev.structured);
          setDone(true);
        } else if (ev.type === "error") {
          setError(ev.message ?? "분석 실패");
          setDone(true);
        }
      } catch {}
    };

    ws.onclose = () => setDone(true);
    ws.onerror = () => {
      setError("연결 오류");
      setDone(true);
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [analyzeId]);

  return { output, done, error, structured };
}
