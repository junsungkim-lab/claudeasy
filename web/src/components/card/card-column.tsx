import { CheckCircle2, XCircle, Circle, Loader2, AlertCircle, Play, Square, ExternalLink, Wrench, RotateCcw, MessageCircle } from "lucide-react";
import { useUIStore } from "@/stores/ui-store";
import { api } from "@/api/client";
import { cn } from "@/lib/utils";
import { useArtifactWs } from "@/hooks/sockets/use-artifact-ws";
import type { Card } from "@/api/client";

const STATUS_CONFIG = {
  done: { icon: CheckCircle2, color: "text-emerald-400", dot: "bg-emerald-400", label: "완료" },
  error: { icon: XCircle, color: "text-red-400", dot: "bg-red-400", label: "오류" },
  in_progress: { icon: Loader2, color: "text-blue-400", dot: "bg-blue-400", label: "실행 중", spin: true },
  awaiting_approval: { icon: AlertCircle, color: "text-amber-400", dot: "bg-amber-400", label: "승인 대기" },
  rejected: { icon: XCircle, color: "text-zinc-500", dot: "bg-zinc-600", label: "거절됨" },
  backlog: { icon: Circle, color: "text-zinc-600", dot: "bg-zinc-700", label: "대기" },
};

function ArtifactControls({ card }: { card: Card }) {
  const hasArtifact = card.status === "done" && !!card.run_command;
  const { artState, setArtState, livePort, portRemapped, stderrTail } = useArtifactWs(card.id, hasArtifact);

  if (!hasArtifact) return null;

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

  return (
    <div className="mt-2 space-y-1" onClick={(e) => e.stopPropagation()}>
      {portRemapped && (
        <p className="text-[10px] text-amber-500">
          포트 {portRemapped.from} 사용 중 → {portRemapped.to}으로 실행했어요
        </p>
      )}
      {artState === "exited_error" && stderrTail && (
        <p className="text-[10px] text-red-400 font-mono line-clamp-1">
          {stderrTail.split("\n").slice(-1)[0]}
        </p>
      )}
      <div className="flex items-center gap-2 flex-wrap">
        {artState === "running" ? (
          <>
            <button
              onClick={handleStop}
              className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-md font-medium bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
            >
              <Square size={9} /> 중지
            </button>
            {displayPort && (
              <a
                href={`http://localhost:${displayPort}`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 text-[10px] text-indigo-400 hover:text-indigo-300"
              >
                <ExternalLink size={9} /> :{displayPort}
              </a>
            )}
            <span className="flex items-center gap-1 text-[10px] text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> 실행 중
            </span>
          </>
        ) : artState === "starting" || artState === "stopping" ? (
          <span className="flex items-center gap-1 text-[10px] text-gray-400">
            <Loader2 size={9} className="animate-spin" />
            {artState === "starting" ? "시작 중..." : "멈추는 중..."}
          </span>
        ) : artState === "exited_error" ? (
          <>
            <button
              onClick={handleAutoFix}
              className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-md font-medium bg-orange-500/20 text-orange-400 hover:bg-orange-500/30 transition-colors"
            >
              <Wrench size={9} /> 자동 수정 후 재실행
            </button>
            <button
              onClick={handleRun}
              className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-md font-medium bg-gray-500/20 text-gray-400 hover:bg-gray-500/30 transition-colors"
            >
              <RotateCcw size={9} /> 재시도
            </button>
          </>
        ) : (
          <button
            onClick={handleRun}
            className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-md font-medium bg-indigo-500/20 text-indigo-400 hover:bg-indigo-500/30 transition-colors"
          >
            <Play size={9} /> 실행하기
          </button>
        )}
      </div>
    </div>
  );
}

export function CardColumns({ cards, pendingRepliesMap = {} }: { cards: Card[]; pendingRepliesMap?: Record<number, number> }) {
  const { setActiveCard } = useUIStore();
  const done = cards.filter(c => c.status === "done").length;

  return (
    <div className="h-full overflow-y-auto bg-gray-50">
      <div className="max-w-2xl mx-auto px-6 py-6">
        {/* Progress header */}
        {cards.length > 0 && (
          <div className="flex items-center justify-between gap-3 mb-8">
            <span className="text-[12px] text-gray-500 font-medium">
              {done} / {cards.length} 완료
            </span>
            <div className="flex-1 h-px bg-gray-200 relative overflow-hidden rounded-full">
              <div
                className="absolute inset-y-0 left-0 bg-emerald-500 transition-all duration-500"
                style={{ width: `${cards.length ? (done / cards.length) * 100 : 0}%` }}
              />
            </div>
            <span className="text-[12px] text-gray-500 font-medium">
              {cards.length ? Math.round((done / cards.length) * 100) : 0}%
            </span>
          </div>
        )}

        {/* Pipeline trace list */}
        <div className="relative">
          {cards.length > 0 && (
            <div className="absolute left-[11px] top-3 bottom-3 w-px bg-gray-200" />
          )}

          <div className="space-y-1">
            {cards.map((card) => {
              const cfg = STATUS_CONFIG[card.status as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.backlog;
              const Icon = cfg.icon;
              const isRunning = card.status === "in_progress";
              const pendingCount = pendingRepliesMap[card.id] ?? 0;

              return (
                <button
                  key={card.id}
                  onClick={() => setActiveCard(card.id)}
                  className={cn(
                    "w-full text-left flex items-start gap-3 px-3 py-3 rounded-lg transition-all duration-150 group",
                    "hover:bg-white/[0.03]",
                    isRunning && "bg-blue-500/[0.04] border border-blue-500/20",
                    !isRunning && "border border-transparent",
                    card.status === "done" && "opacity-75 hover:opacity-100",
                    card.status === "rejected" && "opacity-40 hover:opacity-60",
                    pendingCount > 0 && "ring-1 ring-amber-400/50"
                  )}
                >
                  {/* Status icon */}
                  <div className="mt-[3px] relative z-10 shrink-0">
                    <Icon
                      size={14}
                      className={cn(cfg.color, (cfg as any).spin && "animate-spin")}
                    />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 flex-wrap flex-1 min-w-0">
                        <span
                          className={cn(
                            "text-[13px] font-medium leading-5 truncate",
                            card.status === "done"
                              ? "text-gray-900"
                              : card.status === "error"
                              ? "text-red-300"
                              : card.status === "in_progress"
                              ? "text-blue-200"
                              : "text-gray-500"
                          )}
                        >
                          {card.title}
                        </span>
                        {card.agent_role && (
                          <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-sm bg-indigo-500/15 text-indigo-400 font-medium">
                            {card.agent_role}
                          </span>
                        )}
                      </div>
                      {pendingCount > 0 && (
                        <span className="shrink-0 flex items-center gap-0.5 text-[10px] text-amber-400 font-medium">
                          <MessageCircle size={10} /> 답변 기다리는 중
                        </span>
                      )}
                    </div>

                    {card.output && card.status === "done" && !card.run_command && (
                      <p className="mt-0.5 text-[11px] text-gray-500 line-clamp-1 font-mono">
                        {card.output.replace(/[#*`]/g, "").slice(0, 80)}
                      </p>
                    )}
                    {isRunning && (
                      <p className="mt-0.5 text-[11px] text-blue-400/70 font-mono">실행 중...</p>
                    )}

                    <ArtifactControls card={card} />
                  </div>

                  {/* Right side */}
                  <div className="shrink-0 flex items-center gap-2">
                    <span className={cn("text-[10px] font-medium", cfg.color)}>
                      {cfg.label}
                    </span>
                    <span className="text-[10px] text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity">
                      →
                    </span>
                  </div>
                </button>
              );
            })}

            {cards.length === 0 && (
              <div className="flex items-center justify-center py-12">
                <span className="text-[12px] text-gray-500">
                  카드가 없습니다
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
