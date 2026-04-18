import { CheckCircle2, XCircle, Loader2, Clock, AlertCircle, ThumbsUp, Palette } from "lucide-react";
import { useUIStore } from "@/stores/ui-store";
import { cn, truncate } from "@/lib/utils";
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

export function TaskCard({ card }: { card: Card }) {
  const { setActiveCard } = useUIStore();
  const meta = STATUS_META[card.status] ?? STATUS_META.backlog;

  return (
    <button
      onClick={() => setActiveCard(card.id)}
      className={cn(
        "w-full text-left p-3 rounded-lg border transition-all duration-150 cursor-pointer",
        meta.border,
        meta.bg
      )}
    >
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5">{meta.icon}</div>
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-medium text-gray-900 leading-[1.4] line-clamp-2 mb-1.5">
            {card.title}
          </p>
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
          </div>
          {card.output && (
            <p className="text-[11px] text-gray-500 mt-1.5 line-clamp-2 leading-relaxed font-mono">
              {truncate(card.output.replace(/[#*`]/g, ""), 110)}
            </p>
          )}
        </div>
      </div>
    </button>
  );
}
