import { CheckCircle2, XCircle, Circle, Loader2, AlertCircle } from "lucide-react";
import { useUIStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";
import type { Card } from "@/api/client";

const STATUS_CONFIG = {
  done: { icon: CheckCircle2, color: "text-emerald-400", dot: "bg-emerald-400", label: "완료" },
  error: { icon: XCircle, color: "text-red-400", dot: "bg-red-400", label: "오류" },
  in_progress: { icon: Loader2, color: "text-blue-400", dot: "bg-blue-400", label: "실행 중", spin: true },
  awaiting_approval: { icon: AlertCircle, color: "text-amber-400", dot: "bg-amber-400", label: "승인 대기" },
  rejected: { icon: XCircle, color: "text-zinc-500", dot: "bg-zinc-600", label: "거절됨" },
  backlog: { icon: Circle, color: "text-zinc-600", dot: "bg-zinc-700", label: "대기" },
};

export function CardColumns({ cards }: { cards: Card[] }) {
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
          {/* Vertical connecting line */}
          {cards.length > 0 && (
            <div className="absolute left-[11px] top-3 bottom-3 w-px bg-gray-200" />
          )}

          <div className="space-y-1">
            {cards.map((card) => {
              const cfg = STATUS_CONFIG[card.status as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.backlog;
              const Icon = cfg.icon;
              const isRunning = card.status === "in_progress";

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
                    card.status === "rejected" && "opacity-40 hover:opacity-60"
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
                    <div className="flex items-center gap-2 flex-wrap">
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
                    {card.output && card.status === "done" && (
                      <p className="mt-0.5 text-[11px] text-gray-500 line-clamp-1 font-mono">
                        {card.output.replace(/[#*`]/g, "").slice(0, 80)}
                      </p>
                    )}
                    {isRunning && (
                      <p className="mt-0.5 text-[11px] text-blue-400/70 font-mono">실행 중...</p>
                    )}
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
