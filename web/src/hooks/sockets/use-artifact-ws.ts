import { useState, useEffect, useRef } from "react";
import { wsUrl } from "@/api/client";

export type ArtifactState = "idle" | "starting" | "running" | "stopping" | "exited_ok" | "exited_error";

export function useArtifactWs(cardId: number, enabled: boolean) {
  const [artState, setArtState] = useState<ArtifactState>("idle");
  const [livePort, setLivePort] = useState<number | null>(null);
  const [portRemapped, setPortRemapped] = useState<{ from: number; to: number } | null>(null);
  const [stderrTail, setStderrTail] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const ws = new WebSocket(wsUrl(`/ws/card/${cardId}`));
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data);
        if (ev.type === "artifact_started") {
          setArtState("running");
          setLivePort(ev.port ?? null);
          setPortRemapped(null);
          setStderrTail(null);
        } else if (ev.type === "artifact_stopped") {
          setArtState("idle");
        } else if (ev.type === "artifact_completed") {
          setArtState("exited_ok");
        } else if (ev.type === "artifact_failed") {
          setArtState("exited_error");
          setStderrTail(ev.stderr_tail ?? null);
        } else if (ev.type === "artifact_exited") {
          setArtState(ev.rc === 0 ? "idle" : "exited_error");
          if (ev.rc !== 0) setStderrTail(ev.stderr_tail ?? null);
        } else if (ev.type === "port_remapped") {
          setPortRemapped({ from: ev.from, to: ev.to });
          setLivePort(ev.to);
        }
      } catch {}
    };
    ws.onerror = () => ws.close();

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [cardId, enabled]);

  return { artState, setArtState, livePort, portRemapped, stderrTail };
}
