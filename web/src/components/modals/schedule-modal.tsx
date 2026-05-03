import { useState, useEffect } from "react";
import { Clock, ChevronDown, ChevronUp } from "lucide-react";
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

const DAYS = [
  { label: "일", value: 0 },
  { label: "월", value: 1 },
  { label: "화", value: 2 },
  { label: "수", value: 3 },
  { label: "목", value: 4 },
  { label: "금", value: 5 },
  { label: "토", value: 6 },
];

function buildCron(hour: number, minute: number, days: number[]): string {
  if (days.length === 0 || days.length === 7) {
    return `${minute} ${hour} * * *`;
  }
  return `${minute} ${hour} * * ${days.join(",")}`;
}

function parseCronToTime(expr: string): { hour: number; minute: number; days: number[] } | null {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return null;
  const [min, hr, , , dayPart] = parts;
  if (isNaN(Number(min)) || isNaN(Number(hr))) return null;
  let days: number[] = [];
  if (dayPart === "*") {
    days = [];
  } else {
    days = dayPart.split(",").map(Number).filter((d) => !isNaN(d));
  }
  return { hour: Number(hr), minute: Number(min), days };
}

export function ScheduleModal() {
  const { scheduleModalBoardId, closeScheduleModal } = useUIStore();
  const boardId = scheduleModalBoardId;

  const { data: schedule } = useSchedule(boardId);
  const { mutate: setSchedule, isPending: setting } = useSetSchedule();
  const { mutate: deleteSchedule, isPending: deleting } = useDeleteSchedule();

  const [cronExpr, setCronExpr] = useState("");
  const [approvalMode, setApprovalMode] = useState<"auto" | "manual">("auto");
  const [showAdvanced, setShowAdvanced] = useState(false);

  // 시각 선택기 상태
  const [hour, setHour] = useState(9);
  const [minute, setMinute] = useState(0);
  const [selectedDays, setSelectedDays] = useState<number[]>([]);
  const [useTimeSelector, setUseTimeSelector] = useState(true);

  useEffect(() => {
    if (schedule) {
      const expr = schedule.cron_expr ?? "";
      setCronExpr(expr);
      setApprovalMode(schedule.approval_mode);
      const parsed = expr ? parseCronToTime(expr) : null;
      if (parsed) {
        setHour(parsed.hour);
        setMinute(parsed.minute);
        setSelectedDays(parsed.days);
        setUseTimeSelector(true);
      } else if (expr) {
        setUseTimeSelector(false);
        setShowAdvanced(true);
      }
    }
  }, [schedule]);

  const toggleDay = (day: number) => {
    setSelectedDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day].sort()
    );
  };

  const effectiveCron = useTimeSelector ? buildCron(hour, minute, selectedDays) : cronExpr;

  const handlePreset = (value: string) => {
    const parsed = parseCronToTime(value);
    if (parsed) {
      setHour(parsed.hour);
      setMinute(parsed.minute);
      setSelectedDays(parsed.days);
      setUseTimeSelector(true);
    }
    setCronExpr(value);
  };

  const handleSave = () => {
    if (!boardId || !effectiveCron.trim()) return;
    setSchedule(
      { boardId, cron_expr: effectiveCron.trim(), approval_mode: approvalMode },
      { onSuccess: closeScheduleModal }
    );
  };

  const handleDelete = () => {
    if (!boardId) return;
    deleteSchedule(boardId, { onSuccess: closeScheduleModal });
  };

  const dayLabel = selectedDays.length === 0 || selectedDays.length === 7
    ? "매일"
    : selectedDays.map((d) => DAYS[d].label).join("·") + "요일";
  const timeLabel = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;

  return (
    <Dialog
      open={!!boardId}
      onClose={closeScheduleModal}
      title="스케줄 설정"
      className="max-w-sm"
    >
      <div className="p-4 space-y-4">
        {/* 빠른 프리셋 */}
        <div>
          <label className="text-xs font-medium text-gray-500 mb-1.5 block">
            빠른 선택
          </label>
          <div className="flex flex-wrap gap-1.5">
            {PRESETS.map((p) => (
              <button
                key={p.value}
                onClick={() => handlePreset(p.value)}
                className={`text-[10px] px-2 py-1 rounded-md border transition-colors ${
                  effectiveCron === p.value
                    ? "bg-indigo-50 border-indigo-300 text-indigo-600"
                    : "bg-gray-50 border-gray-200 text-gray-500 hover:text-gray-900"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* 시각 선택기 */}
        <div>
          <label className="text-xs font-medium text-gray-500 mb-2 block">
            시간 직접 선택 — <span className="text-indigo-500">{dayLabel} {timeLabel}</span>
          </label>
          <div className="flex gap-1 mb-2 flex-wrap">
            {DAYS.map((d) => (
              <button
                key={d.value}
                onClick={() => toggleDay(d.value)}
                className={`w-7 h-7 text-[10px] rounded-md border transition-colors ${
                  selectedDays.includes(d.value)
                    ? "bg-indigo-500 border-indigo-500 text-white"
                    : "bg-gray-50 border-gray-200 text-gray-500 hover:bg-gray-100"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <select
              value={hour}
              onChange={(e) => { setHour(Number(e.target.value)); setUseTimeSelector(true); }}
              className="flex-1 text-xs border border-gray-200 rounded-md px-2 py-1.5 bg-white text-gray-900 outline-none focus:border-indigo-300"
            >
              {Array.from({ length: 24 }, (_, i) => (
                <option key={i} value={i}>{String(i).padStart(2, "0")}시</option>
              ))}
            </select>
            <span className="text-gray-400 text-xs">:</span>
            <select
              value={minute}
              onChange={(e) => { setMinute(Number(e.target.value)); setUseTimeSelector(true); }}
              className="flex-1 text-xs border border-gray-200 rounded-md px-2 py-1.5 bg-white text-gray-900 outline-none focus:border-indigo-300"
            >
              {[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map((m) => (
                <option key={m} value={m}>{String(m).padStart(2, "0")}분</option>
              ))}
            </select>
          </div>
        </div>

        {/* 실행 모드 */}
        <div>
          <label className="text-xs font-medium text-gray-500 mb-1.5 block">
            실행 방식
          </label>
          <div className="flex gap-2">
            {(["auto", "manual"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setApprovalMode(m)}
                className={`flex-1 py-1.5 text-xs rounded-md border transition-colors ${
                  approvalMode === m
                    ? "border-indigo-500 bg-indigo-500/10 text-indigo-400"
                    : "border-gray-200 text-gray-500 hover:bg-gray-100"
                }`}
              >
                {m === "auto" ? "바로 실행" : "단계마다 확인"}
              </button>
            ))}
          </div>
        </div>

        {/* 고급: cron 직접 입력 */}
        <button
          className="w-full flex items-center justify-between text-[10px] text-gray-400 hover:text-gray-600 transition-colors"
          onClick={() => setShowAdvanced(!showAdvanced)}
        >
          <span>고급: Cron 표현식 직접 입력</span>
          {showAdvanced ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
        </button>
        {showAdvanced && (
          <Input
            value={cronExpr}
            onChange={(e) => { setCronExpr(e.target.value); setUseTimeSelector(false); }}
            placeholder="0 9 * * *"
          />
        )}

        <div className="flex gap-2 pt-1">
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!effectiveCron.trim() || setting}
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
