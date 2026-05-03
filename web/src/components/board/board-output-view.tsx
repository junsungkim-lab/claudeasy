import { useState, useEffect, useCallback } from "react";
import { Play, Square, ExternalLink, ArrowLeft, Terminal, Clock, RefreshCw, Folder, AlertTriangle, Plus, Trash2, Link, ListOrdered, Pencil, Check, X } from "lucide-react";
import { useRuns, useRunCards } from "@/hooks/queries/use-runs";
import { useBoards } from "@/hooks/queries/use-boards";
import { useAutomation } from "@/hooks/queries/use-automation";
import { useSchedule, useTriggerSchedule } from "@/hooks/queries/use-schedule";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ArtifactEnvForm } from "./artifact-env-form";
import type { Card } from "@/api/client";

// artifact_검증 경고 마커를 카드 output에서 추출
function _parseArtifactWarnings(output: string | null | undefined): string[] {
  if (!output) return [];
  const m = output.match(/\*\*\[artifact 검증 경고\]\*\*\n((?:- .+\n?)+)/);
  if (!m) return [];
  return m[1].trim().split("\n").map((l) => l.replace(/^- /, "").trim()).filter(Boolean);
}

function ArtifactRow({ card }: { card: Card }) {
  const [running, setRunning] = useState(false);
  const [starting, setStarting] = useState(false);
  const [pid, setPid] = useState<number | null>(null);
  const [port, setPort] = useState<number | null>(null);
  const [envReady, setEnvReady] = useState(true);
  const [runError, setRunError] = useState<string | null>(null);
  const [editingCmd, setEditingCmd] = useState(false);
  const [cmdValue, setCmdValue] = useState(card.run_command ?? "");
  const [savingCmd, setSavingCmd] = useState(false);

  const warnings = _parseArtifactWarnings(card.output);

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

  // card WS 이벤트 구독 (artifact_started / artifact_failed / artifact_stopped)
  useEffect(() => {
    const ws = new WebSocket(`ws://${location.host}/ws/card/${card.id}`);
    ws.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data);
        if (ev.type === "artifact_started") {
          setRunning(true);
          setPid(ev.pid ?? null);
          setPort(ev.port ?? null);
          setRunError(null);
        } else if (ev.type === "artifact_completed") {
          setRunning(false);
          setPid(null);
          if (ev.stdout) setScriptLog(ev.stdout);
        } else if (ev.type === "artifact_failed") {
          setRunning(false);
          setPid(null);
          setRunError(ev.stderr_tail || `종료 코드 ${ev.rc}`);
          if (ev.stderr_tail) setScriptLog(ev.stderr_tail);
        } else if (ev.type === "artifact_stopped") {
          setRunning(false);
          setPid(null);
        }
      } catch {}
    };
    return () => ws.close();
  }, [card.id]);

  const handleRun = useCallback(async () => {
    setRunError(null);
    setStarting(true);
    try {
      const res = await fetch(`/api/cards/${card.id}/run`, { method: "POST" });
      const data = await res.json();
      if (data.error) { setRunError(data.error); return; }
      if (data.pid) { setRunning(true); setPid(data.pid); }
      if (data.port) setPort(data.port);
    } catch (e: any) {
      setRunError(e?.message ?? "실행 요청 실패");
    } finally {
      setStarting(false);
    }
  }, [card.id]);

  const handleStop = useCallback(async () => {
    await fetch(`/api/cards/${card.id}/stop`, { method: "POST" });
    setRunning(false);
    setPid(null);
    setPort(null);
  }, [card.id]);

  const [autoFixing, setAutoFixing] = useState(false);
  const [fixMsg, setFixMsg] = useState<string | null>(null);
  const [scriptLog, setScriptLog] = useState<string | null>(null);

  const handleSaveCmd = useCallback(async () => {
    if (!cmdValue.trim()) return;
    setSavingCmd(true);
    try {
      const res = await fetch(`/api/cards/${card.id}/run-command`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_command: cmdValue.trim() }),
      });
      const data = await res.json();
      if (data.ok) { setEditingCmd(false); setRunError(null); }
    } catch {}
    finally { setSavingCmd(false); }
  }, [card.id, cmdValue]);

  const handleAutoFix = useCallback(async () => {
    setAutoFixing(true);
    setRunError(null);
    setFixMsg(null);
    try {
      const res = await fetch(`/api/cards/${card.id}/auto-fix`, { method: "POST" });
      const data = await res.json();
      if (data.error) { setRunError(data.error); return; }
      if (data.ok) {
        setCmdValue(data.fixed_cmd);
        setFixMsg(data.fix_reason);
        if (data.run?.pid) { setRunning(true); setPid(data.run.pid); }
        if (data.run?.port) setPort(data.run.port);
        if (data.run?.error) setRunError(data.run.error);
      }
    } catch (e: any) {
      setRunError(e?.message ?? "자동 수정 실패");
    } finally {
      setAutoFixing(false);
    }
  }, [card.id]);

  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">{card.title}</p>
          <div className="flex items-center gap-1.5 mt-0.5">
            <p className="text-[11px] text-gray-400 font-mono truncate">{card.artifact_cwd}</p>
            {warnings.length > 0 && (
              <span
                title={warnings.join("\n")}
                className="inline-flex items-center gap-0.5 text-[10px] text-amber-600 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5 cursor-help shrink-0"
              >
                <AlertTriangle size={9} /> 경고 {warnings.length}
              </span>
            )}
          </div>
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

      {editingCmd ? (
        <div className="flex items-center gap-1.5 bg-gray-50 rounded-lg px-3 py-1.5">
          <Terminal size={12} className="text-gray-400 shrink-0" />
          <input
            className="flex-1 text-[11px] font-mono bg-transparent outline-none text-gray-900 min-w-0"
            value={cmdValue}
            onChange={(e) => setCmdValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSaveCmd();
              if (e.key === "Escape") { setEditingCmd(false); setCmdValue(card.run_command ?? ""); }
            }}
            autoFocus
          />
          <button onClick={handleSaveCmd} disabled={savingCmd} className="text-emerald-600 hover:text-emerald-700 shrink-0 p-0.5">
            <Check size={13} />
          </button>
          <button onClick={() => { setEditingCmd(false); setCmdValue(card.run_command ?? ""); }} className="text-gray-400 hover:text-gray-600 shrink-0 p-0.5">
            <X size={13} />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2 group">
          <Terminal size={12} className="text-gray-400 shrink-0" />
          <span className="text-[11px] font-mono text-gray-700 truncate flex-1">{cmdValue}</span>
          <button
            onClick={() => setEditingCmd(true)}
            className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-gray-700 shrink-0"
            title="명령어 수정"
          >
            <Pencil size={11} />
          </button>
        </div>
      )}

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
            disabled={!envReady || starting}
            title={!envReady ? "환경 변수를 먼저 설정해주세요" : undefined}
            className="h-7 px-3 text-[11px]"
          >
            {starting
              ? <><span className="w-2 h-2 rounded-full bg-white animate-ping mr-1" />시작 중...</>
              : <><Play size={11} />{card.artifact_type === "server" ? "서버 실행" : "실행하기"}</>
            }
          </Button>
        )}
      </div>

      {fixMsg && !runError && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
          <p className="text-[10px] text-emerald-700 font-medium">✓ 자동 수정 완료 — {fixMsg}</p>
        </div>
      )}

      {running && (
        <div className="bg-gray-900 rounded-lg px-3 py-2">
          <p className="text-[10px] text-gray-400 mb-1 font-mono">실행 로그</p>
          <p className="text-[10px] text-green-400 font-mono animate-pulse">● 실행 중...</p>
        </div>
      )}

      {!running && scriptLog && (
        <div className="bg-gray-900 rounded-lg px-3 py-2">
          <p className="text-[10px] text-gray-400 mb-1.5 font-mono">실행 로그</p>
          <pre className="text-[10px] text-green-300 font-mono whitespace-pre-wrap break-all max-h-48 overflow-y-auto">{scriptLog}</pre>
        </div>
      )}

      {runError && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] font-semibold text-red-700">실행 실패</p>
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                onClick={handleAutoFix}
                disabled={autoFixing}
                className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-md bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-60 transition-colors font-medium"
              >
                {autoFixing
                  ? <><span className="w-1.5 h-1.5 rounded-full bg-white animate-ping mr-0.5" />수정 중...</>
                  : <>🔧 자동 수정 후 재실행</>
                }
              </button>
              <button
                onClick={() => { setEditingCmd(true); setRunError(null); }}
                className="text-[10px] px-2 py-1 rounded-md bg-red-100 text-red-600 hover:bg-red-200 transition-colors"
              >
                직접 수정
              </button>
            </div>
          </div>
          <pre className="text-[10px] text-red-500 font-mono whitespace-pre-wrap break-all max-h-20 overflow-y-auto">{runError}</pre>
        </div>
      )}
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

interface TopicQueueItem {
  type: "topic" | "url";
  value: string;
  detail?: string;
}

function TopicQueuePanel({ boardId }: { boardId: number }) {
  const [queue, setQueue] = useState<TopicQueueItem[] | null>(null);
  const [history, setHistory] = useState<TopicQueueItem[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [inputDetail, setInputDetail] = useState("");
  const [adding, setAdding] = useState(false);
  const [hasQueue, setHasQueue] = useState<boolean | null>(null); // null=로딩중, false=없음, true=있음
  const [initing, setIniting] = useState(false);

  const load = useCallback(async () => {
    const res = await fetch(`/api/boards/${boardId}/topic-queue`);
    if (!res.ok) { setHasQueue(false); return; }
    const data = await res.json();
    setHasQueue(true);
    setQueue(data.queue ?? []);
    setHistory((data.history ?? []).slice(-5).reverse());
  }, [boardId]);

  useEffect(() => { load(); }, [load]);

  const handleInit = async () => {
    setIniting(true);
    try {
      const res = await fetch(`/api/boards/${boardId}/topic-queue/init`, { method: "POST" });
      if (res.ok) await load();
    } finally { setIniting(false); }
  };

  const handleAdd = async () => {
    const value = inputValue.trim();
    if (!value) return;
    const isUrl = /^https?:\/\//.test(value);
    setAdding(true);
    try {
      const res = await fetch(`/api/boards/${boardId}/topic-queue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: isUrl ? "url" : "topic", value, detail: inputDetail.trim() }),
      });
      if (res.ok) { setInputValue(""); setInputDetail(""); await load(); }
    } finally { setAdding(false); }
  };

  const handleDelete = async (index: number) => {
    await fetch(`/api/boards/${boardId}/topic-queue/${index}`, { method: "DELETE" });
    await load();
  };

  if (hasQueue === null) return null; // 로딩 중

  // topic_queue.json 없는 보드 → "발행 큐 추가" 버튼만 표시
  if (!hasQueue) {
    return (
      <div className="border border-dashed border-gray-200 rounded-xl p-4 flex items-center justify-between">
        <div>
          <p className="text-[12px] font-medium text-gray-600">발행 대기 큐</p>
          <p className="text-[11px] text-gray-400 mt-0.5">주제/URL을 미리 쌓아두고 순서대로 자동 발행</p>
        </div>
        <Button size="sm" variant="outline" onClick={handleInit} disabled={initing} className="h-8 px-3 text-[11px] shrink-0">
          <Plus size={11} />
          {initing ? "생성 중..." : "큐 추가"}
        </Button>
      </div>
    );
  }

  const safeQueue = queue ?? [];

  return (
    <div className="border border-gray-200 rounded-xl bg-white p-4 space-y-4">
      <div className="flex items-center gap-2">
        <ListOrdered size={13} className="text-indigo-500" />
        <span className="text-[13px] font-semibold text-gray-800">발행 대기 큐</span>
        <span className="ml-auto text-[10px] text-gray-400">{safeQueue.length}개 대기 중</span>
      </div>

      {/* 추가 입력 */}
      <div className="space-y-2">
        <div className="flex gap-2">
          <input
            className="flex-1 text-[12px] border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-400"
            placeholder="주제 텍스트 또는 https:// URL 입력"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleAdd()}
          />
          <Button size="sm" onClick={handleAdd} disabled={adding || !inputValue.trim()} className="h-9 px-3 shrink-0">
            <Plus size={12} /> 추가
          </Button>
        </div>
        <input
          className="w-full text-[11px] border border-gray-200 rounded-lg px-3 py-1.5 text-gray-600 focus:outline-none focus:ring-1 focus:ring-indigo-300"
          placeholder="추가 지시사항 (선택) — 예: 20대 여성 타겟, 가격 강조"
          value={inputDetail}
          onChange={(e) => setInputDetail(e.target.value)}
        />
      </div>

      {/* 대기 목록 */}
      {safeQueue.length === 0 ? (
        <p className="text-[11px] text-gray-400 text-center py-3">대기 중인 항목이 없습니다</p>
      ) : (
        <div className="space-y-1.5">
          {safeQueue.map((item, i) => (
            <div key={i} className="flex items-start gap-2 bg-gray-50 rounded-lg px-3 py-2">
              <span className="text-[10px] text-gray-400 shrink-0 mt-0.5 w-4">{i + 1}</span>
              {item.type === "url"
                ? <Link size={11} className="text-indigo-400 shrink-0 mt-0.5" />
                : <Terminal size={11} className="text-gray-400 shrink-0 mt-0.5" />}
              <div className="flex-1 min-w-0">
                <p className="text-[11px] text-gray-800 truncate">{item.value}</p>
                {item.detail && <p className="text-[10px] text-gray-400 truncate">{item.detail}</p>}
              </div>
              <button onClick={() => handleDelete(i)} className="text-gray-300 hover:text-red-400 transition-colors shrink-0">
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 최근 발행 이력 */}
      {history.length > 0 && (
        <div className="border-t border-gray-100 pt-3 space-y-1">
          <p className="text-[10px] text-gray-400 font-medium">최근 발행</p>
          {history.map((h: any, i) => (
            <div key={i} className="flex items-center gap-2 text-[10px] text-gray-400">
              <span className={h.success ? "text-green-500" : "text-red-400"}>{h.success ? "✓" : "✗"}</span>
              <span className="truncate">{h.value}</span>
              <span className="shrink-0">{h.date}</span>
            </div>
          ))}
        </div>
      )}
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

        {/* topic_queue.json 있는 보드에만 표시 — 다른 보드는 패널 자체가 null 반환 */}
        <TopicQueuePanel boardId={boardId} />
      </div>
    </div>
  );
}
