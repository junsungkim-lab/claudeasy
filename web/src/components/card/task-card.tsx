import { CheckCircle2, XCircle, Loader2, Clock, AlertCircle, ThumbsUp } from "lucide-react";
import { useUIStore } from "@/stores/ui-store";
import { cn, truncate } from "@/lib/utils";
import type { Card } from "@/api/client";

const STATUS_META: Record<string, { icon: React.ReactNode; border: string; bg: string; badge: string; label: string }> = {
  done: {
    icon: <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />,
    border: "border-emerald-500/25",
    bg: "bg-emerald-950/20 hover:bg-emerald-950/35",
    badge: "bg-emerald-900/50 text-emerald-300",
    label: "완료",
  },
  error: {
    icon: <XCircle size={13} className="text-red-400 shrink-0" />,
    border: "border-red-500/25",
    bg: "bg-red-950/20 hover:bg-red-950/35",
    badge: "bg-red-900/50 text-red-300",
    label: "오류",
  },
  in_progress: {
    icon: <Loader2 size={13} className="text-blue-400 animate-spin shrink-0" />,
    border: "border-blue-500/30",
    bg: "bg-blue-950/20 hover:bg-blue-950/35",
    badge: "bg-blue-900/50 text-blue-300",
    label: "진행 중",
  },
  awaiting_approval: {
    icon: <ThumbsUp size={13} className="text-amber-400 shrink-0" />,
    border: "border-amber-500/30",
    bg: "bg-amber-950/20 hover:bg-amber-950/35",
    badge: "bg-amber-900/50 text-amber-300",
    label: "승인 대기",
  },
  rejected: {
    icon: <XCircle size={13} className="text-red-400/70 shrink-0" />,
    border: "border-red-500/15",
    bg: "bg-red-950/10 hover:bg-red-950/20",
    badge: "bg-red-900/40 text-red-400",
    label: "거절됨",
  },
  backlog: {
    icon: <Clock size={13} className="text-zinc-500 shrink-0" />,
    border: "border-[--color-border]",
    bg: "bg-[--color-card] hover:bg-[--color-accent]",
    badge: "bg-zinc-800 text-zinc-400",
    label: "대기",
  },
};

export function TaskCard({ card }: { card: Card }) {
  const { setActiveCard } = useUIStore();
  const meta = STATUS_META[card.status] ?? STATUS_META.backlog;

  return (
    <button
      onClick={() => setActiveCard(card.id)}
      className={cn(
        "w-full text-left p-3 rounded-xl border transition-all duration-150 shadow-sm hover:shadow-md hover:-translate-y-px cursor-pointer",
        meta.border,
        meta.bg
      )}
    >
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5">{meta.icon}</div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-[--color-foreground] leading-[1.45] line-clamp-2 mb-1.5">
            {card.title}
          </p>
          <div className="flex items-center gap-1.5 flex-wrap">
            {card.agent_role && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-indigo-900/40 text-indigo-300 font-medium">
                {card.agent_role}
              </span>
            )}
            <span className={cn("text-[10px] px-1.5 py-0.5 rounded-md font-medium", meta.badge)}>
              {meta.label}
            </span>
          </div>
          {card.output && (
            <p className="text-[10px] text-[--color-muted-foreground] mt-1.5 line-clamp-2 leading-relaxed">
              {truncate(card.output.replace(/[#*`]/g, ""), 110)}
            </p>
          )}
        </div>
      </div>
    </button>
  );
}
