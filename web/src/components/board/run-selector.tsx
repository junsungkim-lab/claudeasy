import { ChevronDown, RotateCcw } from "lucide-react";
import { useRuns, useRerun } from "@/hooks/queries/use-runs";
import { useUIStore } from "@/stores/ui-store";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/utils";

const RUN_STATUS_COLORS: Record<string, string> = {
  done: "text-emerald-400",
  running: "text-blue-400",
  error: "text-red-400",
  generating: "text-amber-400 animate-pulse",
  ready: "text-zinc-400",
};

export function RunSelector({ boardId }: { boardId: number }) {
  const { selectedRunId, setSelectedRun } = useUIStore();
  const { data: runs = [] } = useRuns(boardId);
  const { mutate: rerun, isPending: rerunning } = useRerun();

  const current = runs.find((r) => r.id === selectedRunId) ?? runs[0];

  if (runs.length === 0) return null;

  return (
    <div className="flex items-center gap-2">
      <div className="relative">
        <select
          value={current?.id ?? ""}
          onChange={(e) => setSelectedRun(Number(e.target.value))}
          className="appearance-none bg-[--color-muted] border border-[--color-border] rounded-md pl-3 pr-7 py-1 text-xs text-[--color-foreground] focus:outline-none focus:ring-1 focus:ring-[--color-ring] cursor-pointer"
        >
          {runs.map((r) => (
            <option key={r.id} value={r.id}>
              Run #{r.id} · {r.trigger} · {formatDateTime(r.created_at)}
            </option>
          ))}
        </select>
        <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-[--color-muted-foreground] pointer-events-none" />
      </div>

      {current && (
        <span className={`text-xs font-medium ${RUN_STATUS_COLORS[current.status] ?? "text-zinc-400"}`}>
          {current.status}
        </span>
      )}

      <Button
        size="icon"
        variant="ghost"
        onClick={() => rerun(boardId)}
        disabled={rerunning}
        title="재실행"
      >
        <RotateCcw size={13} className={rerunning ? "animate-spin" : ""} />
      </Button>
    </div>
  );
}
