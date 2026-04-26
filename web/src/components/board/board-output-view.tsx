import { useState, useEffect } from "react";
import { Play, Square, ExternalLink, ArrowLeft, Terminal, Clock, RefreshCw, Folder } from "lucide-react";
import { useRuns, useRunCards } from "@/hooks/queries/use-runs";
import { useBoards } from "@/hooks/queries/use-boards";
import { useAutomation } from "@/hooks/queries/use-automation";
import { useSchedule, useTriggerSchedule } from "@/hooks/queries/use-schedule";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ArtifactEnvForm } from "./artifact-env-form";
import type { Card } from "@/api/client";

function ArtifactRow({ card }: { card: Card }) {
  const [running, setRunning] = useState(false);
  const [pid, setPid] = useState<number | null>(null);
  const [port, setPort] = useState<number | null>(null);
  const [envReady, setEnvReady] = useState(true);

  useEffect(() => {
    fetch(`/api/cards/${card.id}/run-status`)
      .then((r) => r.json())
      .then((d) => {
        setRunning(d.running);
        setPid(d.pid ?? null);
        setPort(d.port ?? null);
      })
      .catch(() => {});
  }, [card.id]);

  const handleRun = async () => {
    const res = await fetch(`/api/cards/${card.id}/run`, { method: "POST" });
    const data = await res.json();
    if (data.pid) { setRunning(true); setPid(data.pid); }
    if (data.port) setPort(data.port);
  };

  const handleStop = async () => {
    await fetch(`/api/cards/${card.id}/stop`, { method: "POST" });
    setRunning(false);
    setPid(null);
    setPort(null);
  };

  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">{card.title}</p>
          <p className="text-[11px] text-gray-400 mt-0.5 font-mono truncate">{card.artifact_cwd}</p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <Badge variant="secondary" className="text-[10px] h-5">{card.agent_role}</Badge>
          <Badge
            variant="secondary"
            className={cn("text-[10px] h-5", card.artifact_type === "server" ? "bg-blue-100 text-blue-700" : "bg-violet-100 text-violet-700")}
          >
            {card.artifact_type === "server" ? "서버" : "스크립트"}
          </Badge>
        </div>
      </div>

      <ArtifactEnvForm cardId={card.id} onReadyChange={setEnvReady} onSaved={() => setEnvReady(true)} />

      <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2">
        <Terminal size={12} className="text-gray-400 shrink-0" />
        <span className="text-[11px] font-mono text-gray-700 truncate">{card.run_command}</span>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={cn("w-2 h-2 rounded-full", running ? "bg-green-400 animate-pulse" : "bg-gray-300")} />
          <span className="text-[11px] text-gray-500">{running ? "실행 중" : "대기"}</span>
          {port && running && (
            <a
              href={`http://localhost:${port}`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-0.5 text-[11px] text-indigo-500 hover:text-indigo-700"
            >
              :{port} <ExternalLink size={9} />
            </a>
          )}
          {pid && <span className="text-[10px] text-gray-400">PID {pid}</span>}
        </div>
        {running ? (
          <Button size="sm" variant="destructive" onClick={handleStop} className="h-7 px-3 text-[11px]">
            <Square size={11} /> 중지
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={handleRun}
            disabled={!envReady}
            title={!envReady ? "환경 변수를 먼저 설정해주세요" : undefined}
            className="h-7 px-3 text-[11px]"
          >
            <Play size={11} />
            {card.artifact_type === "server" ? "서버 실행" : "실행하기"}
          </Button>
        )}
      </div>
    </div>
  );
}

function AutomationOutputView({ boardId }: { boardId: number }) {
  const { data: info } = useAutomation(boardId);
  const { data: schedule } = useSchedule(boardId);
  const trigger = useTriggerSchedule();
  const [envValues, setEnvValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSaveEnv = async () => {
    if (!Object.keys(envValues).length) return;
    setSaving(true);
    try {
      await fetch(`/api/boards/${boardId}/env`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(envValues),
      });
      setEnvValues({});
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* 도구 디렉터리 */}
      {info?.tool_dir && (
        <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Folder size={13} className="text-gray-400" />
            <span className="text-[11px] font-semibold text-gray-700">작업 디렉터리</span>
          </div>
          <p className="text-[11px] font-mono text-gray-600 bg-gray-50 rounded px-2 py-1 truncate">{info.tool_dir}</p>

          {/* 스크립트 목록 */}
          {info.scripts.length > 0 && (
            <div>
              <p className="text-[10px] text-gray-400 mb-1.5">도구 스크립트 ({info.scripts.length}개)</p>
              <div className="space-y-1">
                {info.scripts.map((s) => (
                  <div key={s} className="flex items-center gap-1.5 text-[11px] font-mono text-gray-600">
                    <Terminal size={10} className="text-gray-300" />
                    {s}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 스케줄 상태 + 즉시 실행 */}
      <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock size={13} className="text-gray-400" />
            <span className="text-[11px] font-semibold text-gray-700">스케줄</span>
            {schedule?.cron_expr ? (
              <Badge variant="secondary" className="text-[10px] h-5 font-mono">{schedule.cron_expr}</Badge>
            ) : (
              <span className="text-[10px] text-gray-400">미등록</span>
            )}
          </div>
          <Button
            size="sm"
            onClick={() => trigger.mutate(boardId)}
            disabled={trigger.isPending}
            className="h-7 px-3 text-[11px]"
          >
            <RefreshCw size={11} className={trigger.isPending ? "animate-spin" : ""} />
            지금 실행
          </Button>
        </div>
        {schedule?.next_run_at && (
          <p className="text-[10px] text-gray-400">
            다음 실행: {new Date(schedule.next_run_at).toLocaleString("ko-KR")}
          </p>
        )}
      </div>

      {/* 보드 환경 변수 */}
      <div className="border border-indigo-200 rounded-xl bg-white p-4 space-y-2">
        <p className="text-[11px] font-semibold text-indigo-800">환경 변수 (.env)</p>
        <p className="text-[10px] text-gray-400">KEY=VALUE 형태로 입력하면 tool_dir/.env에 저장됩니다.</p>
        <textarea
          className="w-full text-[11px] font-mono border border-gray-200 rounded p-2 h-24 resize-none focus:outline-none focus:ring-1 focus:ring-indigo-400"
          placeholder={"API_KEY=your_key\nTOKEN=your_token"}
          value={Object.entries(envValues).map(([k, v]) => `${k}=${v}`).join("\n")}
          onChange={(e) => {
            const parsed: Record<string, string> = {};
            e.target.value.split("\n").forEach((line) => {
              const idx = line.indexOf("=");
              if (idx > 0) parsed[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
            });
            setEnvValues(parsed);
          }}
        />
        <Button
          size="sm"
          onClick={handleSaveEnv}
          disabled={saving || !Object.keys(envValues).length}
          className="w-full h-7 text-[11px]"
        >
          {saved ? "저장 완료" : saving ? "저장 중..." : "저장"}
        </Button>
      </div>
    </div>
  );
}

export function BoardOutputView({ boardId }: { boardId: number }) {
  const { data: boards = [] } = useBoards();
  const board = boards.find((b) => b.id === boardId) ?? null;
  const isAutomation = board?.task_kind === "automation";

  const { data: runs = [] } = useRuns(boardId);
  const latestRun = runs[0] ?? null;
  const cards = useRunCards(boardId, latestRun?.id ?? null);

  const artifacts = cards.filter(
    (c) => c.run_command && c.status === "done" && c.artifact_type
  );

  return (
    <div className="h-full overflow-y-auto bg-gray-50">
      <div className="max-w-2xl mx-auto px-6 py-6 space-y-4">
        <button
          onClick={() => { window.location.hash = ""; }}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 transition-colors"
        >
          <ArrowLeft size={13} />
          카드 보기로 돌아가기
        </button>

        <div>
          <h2 className="text-[15px] font-semibold text-gray-900">
            {isAutomation ? "자동화 실행" : "최종 결과물"}
          </h2>
          <p className="text-[12px] text-gray-500 mt-0.5">
            {isAutomation
              ? "자동화 도구 스크립트 목록과 실행 상태입니다."
              : "실행 가능한 산출물 목록입니다."}
          </p>
        </div>

        {isAutomation ? (
          <AutomationOutputView boardId={boardId} />
        ) : artifacts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-gray-400 gap-2">
            <Terminal size={32} className="opacity-30" />
            <p className="text-sm">아직 실행 가능한 결과물이 없습니다.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {artifacts.map((card) => (
              <ArtifactRow key={card.id} card={card} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
