import { useState, useEffect } from "react";
import { Clock } from "lucide-react";
import { useSchedule, useSetSchedule, useDeleteSchedule } from "@/hooks/queries/use-schedule";
import { useUIStore } from "@/stores/ui-store";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const PRESETS = [
  { label: "매일 오전 9시", value: "0 9 * * *" },
  { label: "매주 월요일 오전 9시", value: "0 9 * * 1" },
  { label: "매 시간", value: "0 * * * *" },
  { label: "매 30분", value: "*/30 * * * *" },
];

export function ScheduleModal() {
  const { scheduleModalBoardId, closeScheduleModal } = useUIStore();
  const boardId = scheduleModalBoardId;

  const { data: schedule } = useSchedule(boardId);
  const { mutate: setSchedule, isPending: setting } = useSetSchedule();
  const { mutate: deleteSchedule, isPending: deleting } = useDeleteSchedule();

  const [cronExpr, setCronExpr] = useState("");
  const [approvalMode, setApprovalMode] = useState<"auto" | "manual">("auto");

  useEffect(() => {
    if (schedule) {
      setCronExpr(schedule.cron_expr ?? "");
      setApprovalMode(schedule.approval_mode);
    }
  }, [schedule]);

  const handleSave = () => {
    if (!boardId || !cronExpr.trim()) return;
    setSchedule(
      { boardId, cron_expr: cronExpr.trim(), approval_mode: approvalMode },
      { onSuccess: closeScheduleModal }
    );
  };

  const handleDelete = () => {
    if (!boardId) return;
    deleteSchedule(boardId, { onSuccess: closeScheduleModal });
  };

  return (
    <Dialog
      open={!!boardId}
      onClose={closeScheduleModal}
      title="스케줄 설정"
      className="max-w-sm"
    >
      <div className="p-4 space-y-4">
        <div>
          <label className="text-xs font-medium text-[--color-muted-foreground] mb-1.5 block">
            Cron 표현식
          </label>
          <Input
            value={cronExpr}
            onChange={(e) => setCronExpr(e.target.value)}
            placeholder="0 9 * * *"
          />
          <div className="flex flex-wrap gap-1.5 mt-2">
            {PRESETS.map((p) => (
              <button
                key={p.value}
                onClick={() => setCronExpr(p.value)}
                className="text-[10px] px-2 py-0.5 rounded bg-[--color-muted] text-[--color-muted-foreground] hover:bg-[--color-accent] hover:text-[--color-foreground] transition-colors"
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-xs font-medium text-[--color-muted-foreground] mb-1.5 block">
            실행 모드
          </label>
          <div className="flex gap-2">
            {(["auto", "manual"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setApprovalMode(m)}
                className={`flex-1 py-1.5 text-xs rounded-md border transition-colors ${
                  approvalMode === m
                    ? "border-[--color-primary] bg-indigo-500/10 text-indigo-400"
                    : "border-[--color-border] text-[--color-muted-foreground] hover:bg-[--color-accent]"
                }`}
              >
                {m === "auto" ? "자동 실행" : "수동 승인"}
              </button>
            ))}
          </div>
        </div>

        <div className="flex gap-2 pt-2">
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!cronExpr.trim() || setting}
            className="flex-1"
          >
            <Clock size={13} />
            {setting ? "저장 중..." : "저장"}
          </Button>
          {schedule?.cron_expr && (
            <Button
              size="sm"
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? "삭제 중..." : "삭제"}
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  );
}
