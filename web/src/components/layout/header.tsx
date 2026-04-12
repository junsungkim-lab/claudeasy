import { Terminal, PanelLeft } from "lucide-react";
import { useHealth } from "@/hooks/queries/use-health";
import { useUIStore } from "@/stores/ui-store";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function Header() {
  const { data: health } = useHealth();
  const { toggleSidebar, openTrending } = useUIStore();

  const statusColor =
    !health
      ? "bg-zinc-500"
      : health.claude_cli && health.claude_authed
      ? "bg-emerald-500"
      : health.claude_cli
      ? "bg-amber-400"
      : "bg-red-500";

  const statusText = !health
    ? "서버 연결 중..."
    : !health.claude_cli
    ? "Claude CLI 미설치"
    : !health.claude_authed
    ? `Claude CLI ${health.version ?? ""} (인증 필요)`
    : `Claude CLI ${health.version ?? ""} — 정상`;

  return (
    <header className="h-11 flex items-center justify-between px-4 border-b border-[--color-border] bg-[#111118] shrink-0">
      <div className="flex items-center gap-2">
        <button
          onClick={toggleSidebar}
          className="p-1 rounded text-[--color-muted-foreground] hover:text-[--color-foreground] hover:bg-[--color-accent] transition-colors"
        >
          <PanelLeft size={16} />
        </button>
        <div className="flex items-center gap-1.5">
          <Terminal size={15} className="text-indigo-400" />
          <span className="text-sm font-semibold text-[--color-foreground]">claude-local</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={openTrending}
          className="text-xs text-[--color-muted-foreground] hover:text-[--color-foreground] transition-colors"
        >
          GitHub Trending
        </button>

        <Tooltip content={statusText}>
          <div className="flex items-center gap-1.5 cursor-default">
            <div className={cn("w-2 h-2 rounded-full", statusColor)} />
            <span className="text-xs text-[--color-muted-foreground]">
              {!health ? "연결 중" : health.claude_cli ? "정상" : "오류"}
            </span>
          </div>
        </Tooltip>
      </div>
    </header>
  );
}
