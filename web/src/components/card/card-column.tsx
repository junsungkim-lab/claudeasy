import { Loader2 } from "lucide-react";
import { TaskCard } from "./task-card";
import { cn } from "@/lib/utils";
import type { Card } from "@/api/client";

interface ColumnConfig {
  key: string;
  label: string;
  statuses: string[];
  headerBg: string;
  headerText: string;
  dotColor: string;
  emptyText: string;
}

const COLUMNS: ColumnConfig[] = [
  {
    key: "backlog",
    label: "대기",
    statuses: ["backlog"],
    headerBg: "bg-zinc-800/60",
    headerText: "text-zinc-300",
    dotColor: "bg-zinc-500",
    emptyText: "대기 중인 카드 없음",
  },
  {
    key: "in_progress",
    label: "진행 중",
    statuses: ["in_progress", "awaiting_approval"],
    headerBg: "bg-blue-950/60",
    headerText: "text-blue-300",
    dotColor: "bg-blue-400 animate-pulse",
    emptyText: "진행 중인 카드 없음",
  },
  {
    key: "done",
    label: "완료",
    statuses: ["done"],
    headerBg: "bg-emerald-950/60",
    headerText: "text-emerald-300",
    dotColor: "bg-emerald-400",
    emptyText: "완료된 카드 없음",
  },
  {
    key: "error",
    label: "오류 / 거절",
    statuses: ["error", "rejected"],
    headerBg: "bg-red-950/60",
    headerText: "text-red-300",
    dotColor: "bg-red-400",
    emptyText: "오류 없음",
  },
];

export function CardColumns({ cards }: { cards: Card[] }) {
  const runningCount = cards.filter(
    (c) => c.status === "in_progress" || c.status === "awaiting_approval"
  ).length;
  const doneCount = cards.filter((c) => c.status === "done").length;

  return (
    <div className="flex flex-col h-full">
      {/* 진행 상황 요약 바 */}
      {cards.length > 0 && (
        <div className="px-5 py-2.5 border-b border-[--color-border] bg-[--color-card] flex items-center gap-5">
          <div className="flex items-center gap-2 flex-1 max-w-xs">
            <div className="h-1.5 bg-[--color-muted] rounded-full flex-1 overflow-hidden">
              <div
                className="h-full bg-emerald-500 rounded-full transition-all duration-700"
                style={{ width: `${(doneCount / cards.length) * 100}%` }}
              />
            </div>
            <span className="text-[10px] text-[--color-muted-foreground] shrink-0 tabular-nums">
              {doneCount}/{cards.length} 완료
            </span>
          </div>
          {runningCount > 0 && (
            <div className="flex items-center gap-1.5 text-[11px] text-blue-400 font-medium">
              <Loader2 size={11} className="animate-spin" />
              {runningCount}개 실행 중
            </div>
          )}
        </div>
      )}

      {/* 칸반 칼럼 */}
      <div className="flex gap-4 flex-1 px-5 py-5 overflow-x-auto overflow-y-hidden">
        {COLUMNS.map((col) => {
          const colCards = cards.filter((c) => col.statuses.includes(c.status));

          return (
            <div key={col.key} className="flex flex-col w-64 shrink-0">
              {/* 칼럼 헤더 */}
              <div className={cn("flex items-center gap-2 mb-3 px-3 py-2 rounded-lg", col.headerBg)}>
                <div className={cn("w-2 h-2 rounded-full shrink-0", col.dotColor)} />
                <span className={cn("text-xs font-semibold flex-1", col.headerText)}>
                  {col.label}
                </span>
                <span className="text-[10px] font-medium text-[--color-muted-foreground] bg-black/30 rounded-full px-2 py-0.5">
                  {colCards.length}
                </span>
              </div>

              {/* 카드 목록 */}
              <div className="flex flex-col gap-2 flex-1 overflow-y-auto min-h-[80px]">
                {colCards.map((card) => (
                  <TaskCard key={card.id} card={card} />
                ))}
                {colCards.length === 0 && (
                  <div className="flex items-center justify-center flex-1 min-h-[80px] border border-dashed border-[--color-border] rounded-lg">
                    <span className="text-[10px] text-[--color-muted-foreground]/50">
                      {col.emptyText}
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
