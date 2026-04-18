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
    <div className="flex flex-col h-full bg-gray-50">
      {/* 상태 라인 */}
      <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-200">
        <div className="flex items-center gap-2">
          {isGenerating ? (
            <>
              <Loader2 size={12} className="animate-spin text-blue-400" />
              <span className="text-[12px] font-medium text-blue-400">구성 중</span>
            </>
          ) : (
            <>
              <div className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-[12px] font-medium text-gray-900">준비됨</span>
            </>
          )}
        </div>
        {statusText && (
          <span className="ml-auto text-[11px] text-gray-500 font-mono truncate">
            {statusText.replace(/^[^\s]+\s*/, "")}
          </span>
        )}
      </div>

      {/* 이벤트 로그 */}
      <div className="flex-1 overflow-y-auto px-5 py-4 font-mono text-[12px] space-y-0.5 leading-relaxed">
        {events.length === 0 && (
          <div className="flex items-center gap-2 text-gray-500 animate-pulse">
            <Loader2 size={11} className="animate-spin" />
            <span className="text-[11px]">요청 분석 중...</span>
          </div>
        )}
        {events.map((ev, i) => {
          if (ev.type === "status") {
            return (
              <div key={i} className="text-gray-500">
                <span className="text-indigo-400 mr-2">›</span>
                <span className="text-[11px]">{ev.text}</span>
              </div>
            );
          }
          if (ev.type === "harness_chunk") {
            return (
              <div
                key={i}
                className="text-gray-900 whitespace-pre-wrap pl-3 border-l border-gray-200 text-[11px]"
              >
                {ev.text}
              </div>
            );
          }
          return null;
        })}
        {isGenerating && events.length > 0 && (
          <div className="flex items-center gap-1.5 text-gray-500 mt-1">
            <Loader2 size={10} className="animate-spin" />
            <span className="animate-pulse text-[11px]">생성 중...</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
