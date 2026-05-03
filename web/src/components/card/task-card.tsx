import { CheckCircle2, XCircle, Loader2, Clock, ThumbsUp, Palette, Play, ExternalLink, Square, RotateCcw, Wrench, MessageCircle } from "lucide-react";
import { useUIStore } from "@/stores/ui-store";
import { api } from "@/api/client";
import { cn, truncate } from "@/lib/utils";
import { useArtifactWs } from "@/hooks/sockets/use-artifact-ws";
import type { Card } from "@/api/client";

const STATUS_META: Record<string, { icon: React.ReactNode; border: string; bg: string; badge: string; label: string }> = {
  done: {
    icon: <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />,
    border: "border-emerald-200",
    bg: "bg-emerald-50 hover:bg-emerald-100/70",
    badge: "bg-emerald-100 text-emerald-700",
    label: "완료",
  },
  error: {
    icon: <XCircle size={13} className="text-red-500 shrink-0" />,
    border: "border-red-200",
    bg: "bg-red-50 hover:bg-red-100/70",
    badge: "bg-red-100 text-red-700",
    label: "오류",
  },
  in_progress: {
    icon: <Loader2 size={13} className="text-blue-500 animate-spin shrink-0" />,
    border: "border-blue-200",
    bg: "bg-blue-50 hover:bg-blue-100/70",
    badge: "bg-blue-100 text-blue-700",
    label: "진행 중",
  },
  awaiting_approval: {
    icon: <ThumbsUp size={13} className="text-amber-500 shrink-0" />,
    border: "border-amber-200",
    bg: "bg-amber-50 hover:bg-amber-100/70",
    badge: "bg-amber-100 text-amber-700",
    label: "승인 대기",
  },
  rejected: {
    icon: <XCircle size={13} className="text-gray-400 shrink-0" />,
    border: "border-gray-200",
    bg: "bg-white hover:bg-gray-100",
    badge: "bg-gray-100 text-gray-500",
    label: "거절됨",
  },
  backlog: {
    icon: <Clock size={13} className="text-gray-400 shrink-0" />,
    border: "border-gray-200",
    bg: "bg-white hover:bg-gray-100",
    badge: "bg-gray-100 text-gray-500",
    label: "대기",
  },
};

export function TaskCard({ card, pendingReplies = 0 }: { card: Card; pendingReplies?: number }) {
  const { setActiveCard } = useUIStore();
  const meta = STATUS_META[card.status] ?? STATUS_META.backlog;

  const hasArtifact = card.status === "done" && !!card.run_command;
  const { artState, setArtState, livePort, portRemapped, stderrTail } = useArtifactWs(card.id, hasArtifact);

  const displayPort = livePort ?? card.artifact_port;

  const handleRun = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (artState === "running" || artState === "starting") return;
    setArtState("starting");
    try {
      await api(`/api/cards/${card.id}/run`, { method: "POST" });
    } catch {
      setArtState("idle");
    }
  };

  const handleStop = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setArtState("stopping");
    try {
      await api(`/api/cards/${card.id}/stop`, { method: "POST" });
    } catch {}
  };

  const handleAutoFix = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setArtState("starting");
    try {
      await api(`/api/cards/${card.id}/auto-fix`, { method: "POST" });
    } catch {
      setArtState("idle");
    }
  };

  const borderClass =
    artState === "exited_error" ? "border-red-300" :
    artState === "running" ? "border-emerald-300" :
    meta.border;

  const bgClass =
    artState === "exited_error" ? "bg-red-50 hover:bg-red-100/70" :
    artState === "running" ? "bg-emerald-50 hover:bg-emerald-100/50" :
    meta.bg;

  return (
    <button
      onClick={() => setActiveCard(card.id)}
      className={cn(
        "w-full text-left p-3 rounded-lg border transition-all duration-150 cursor-pointer",
        borderClass,
        bgClass
      )}
    >
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5">{meta.icon}</div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-1 mb-1">
            <p className="text-[12px] font-medium text-gray-900 leading-[1.4] line-clamp-2 flex-1">
              {card.title}
            </p>
            {pendingReplies > 0 && (
              <span className="flex items-center gap-0.5 text-[10px] text-red-500 shrink-0">
                <MessageCircle size={10} />
                {pendingReplies}
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5 flex-wrap">
            {card.agent_role && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-sm bg-indigo-100 text-indigo-600 font-medium">
                {card.agent_role}
              </span>
            )}
            {card.design_system && (
              <span className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-sm bg-violet-50 text-violet-500 font-medium">
                <Palette size={8} />{card.design_system}
              </span>
            )}
            <span className={cn("text-[10px] px-1.5 py-0.5 rounded-sm font-medium", meta.badge)}>
              {meta.label}
            </span>
            {artState === "running" && (
              <span className="flex items-center gap-1 text-[10px] text-emerald-600 font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                실행 중
              </span>
            )}
            {artState === "exited_ok" && (
              <span className="text-[10px] text-emerald-600 font-medium">완료</span>
            )}
            {artState === "exited_error" && (
              <span className="text-[10px] text-red-600 font-medium">꺼짐</span>
            )}
          </div>

          {card.output && artState === "idle" && (
            <p className="text-[11px] text-gray-500 mt-1.5 line-clamp-2 leading-relaxed font-mono">
              {truncate(card.output.replace(/[#*`]/g, ""), 110)}
            </p>
          )}

          {portRemapped && (
            <p className="text-[10px] text-amber-600 mt-1">
              포트 {portRemapped.from} 사용 중 → {portRemapped.to}으로 실행했어요
            </p>
          )}

          {artState === "exited_error" && stderrTail && (
            <p className="text-[10px] text-red-500 mt-1 line-clamp-1 font-mono">
              {stderrTail.split("\n").slice(-1)[0]}
            </p>
          )}

          {hasArtifact && (
            <div className="flex items-center gap-2 mt-2 flex-wrap" onClick={(e) => e.stopPropagation()}>
              {artState === "running" ? (
                <>
                  <button
                    onClick={handleStop}
                    className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-md font-medium bg-red-100 text-red-700 hover:bg-red-200 transition-colors"
                  >
                    <Square size={9} /> 중지
                  </button>
                  {displayPort && (
                    <a
                      href={`http://localhost:${displayPort}`}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1 text-[10px] text-indigo-500 hover:text-indigo-700"
                    >
                      <ExternalLink size={9} /> :{displayPort}
                    </a>
                  )}
                </>
              ) : artState === "starting" || artState === "stopping" ? (
                <span className="flex items-center gap-1 text-[10px] text-gray-500">
                  <Loader2 size={9} className="animate-spin" />
                  {artState === "starting" ? "시작 중..." : "멈추는 중..."}
                </span>
              ) : artState === "exited_error" ? (
                <>
                  <button
                    onClick={handleAutoFix}
                    className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-md font-medium bg-orange-100 text-orange-700 hover:bg-orange-200 transition-colors"
                  >
                    <Wrench size={9} /> 자동 수정 후 재실행
                  </button>
                  <button
                    onClick={handleRun}
                    className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-md font-medium bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors"
                  >
                    <RotateCcw size={9} /> 재시도
                  </button>
                </>
              ) : (
                <button
                  onClick={handleRun}
                  className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-md font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
                >
                  <Play size={9} /> 실행하기
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </button>
  );
}
