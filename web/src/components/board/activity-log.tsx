import { useEffect, useRef } from "react";
import { Loader2, Zap } from "lucide-react";
import type { BoardEvent } from "@/hooks/sockets/use-board-ws";

interface ActivityLogProps {
  statusText: string | null;
  events: BoardEvent[];
  boardStatus: string;
}

export function ActivityLog({ statusText, events, boardStatus }: ActivityLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length, statusText]);

  const isGenerating = boardStatus === "generating";

  return (
    <div className="flex flex-col h-full">
      {/* 상태 헤더 */}
      <div className="flex items-center gap-2 px-5 py-3 border-b border-[--color-border] bg-[--color-card]">
        {isGenerating ? (
          <>
            <Loader2 size={14} className="animate-spin text-indigo-400" />
            <span className="text-sm font-medium text-indigo-400">에이전트 팀 구성 중...</span>
          </>
        ) : (
          <>
            <Zap size={14} className="text-emerald-400" />
            <span className="text-sm font-medium text-emerald-400">준비 완료</span>
          </>
        )}
        {statusText && (
          <span className="ml-2 text-xs text-[--color-muted-foreground] truncate">
            {statusText.replace(/^[^\s]+\s*/, "")}
          </span>
        )}
      </div>

      {/* 이벤트 로그 */}
      <div className="flex-1 overflow-y-auto px-5 py-4 font-mono text-xs space-y-0.5">
        {events.length === 0 && (
          <div className="flex items-center gap-2 text-[--color-muted-foreground] animate-pulse">
            <Loader2 size={12} className="animate-spin" />
            <span>Claude가 요청을 분석 중입니다...</span>
          </div>
        )}
        {events.map((ev, i) => {
          if (ev.type === "status") {
            return (
              <div key={i} className="text-[--color-muted-foreground]">
                <span className="text-indigo-400 mr-2">›</span>
                {ev.text}
              </div>
            );
          }
          if (ev.type === "harness_chunk") {
            return (
              <div key={i} className="text-[--color-foreground] leading-relaxed whitespace-pre-wrap pl-3 border-l border-[--color-border]">
                {ev.text}
              </div>
            );
          }
          return null;
        })}
        {isGenerating && events.length > 0 && (
          <div className="flex items-center gap-1.5 text-[--color-muted-foreground] mt-1">
            <Loader2 size={10} className="animate-spin" />
            <span className="animate-pulse">생성 중...</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
