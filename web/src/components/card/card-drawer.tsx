import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import {
  ThumbsUp, ThumbsDown, RotateCcw, Loader2, MessageSquare, Bot, User,
  Send, ChevronLeft, ChevronRight, Images, ChevronDown, ChevronUp,
  History, HelpCircle, Play, Square, ExternalLink, Plus, Palette,
} from "lucide-react";

function hasUnansweredQuestions(output: string): boolean {
  if (!output || output.length < 50) return false;
  const lines = output.split("\n");
  const questionLines = lines.filter((l) => l.trim().endsWith("?")).length;
  const hasOptions = /\*\*[ABC]\)\*\*|^\s*[-*]?\s*\*?\*?[ABC]\)/m.test(output);
  const hasNumbered = /^\s*\d+\.\s.*\?/m.test(output);
  const hasPhrase = ["확인하고 싶", "어떻게 하실", "어떤 방향", "알려주시면", "말씀해 주시면", "결정해 주세요", "선택해 주세요"].some((p) => output.includes(p));
  return questionLines >= 2 || hasOptions || hasNumbered || hasPhrase;
}

import { useRunCards } from "@/hooks/queries/use-runs";
import { useFeedback, useAddFeedback, useApproveCard, useAskAgent, useCardSlides } from "@/hooks/queries/use-feedback";
import { useCardWs } from "@/hooks/sockets/use-card-ws";
import { useUIStore } from "@/stores/ui-store";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { ClarificationCard } from "@/components/board/clarification-card";
import { EnvInputCard } from "@/components/board/env-input-card";
import { ArtifactEnvForm } from "@/components/board/artifact-env-form";
import type { Feedback } from "@/api/client";

export function CardDrawer() {
  const { activeCardId, selectedBoardId, selectedRunId, setActiveCard } = useUIStore();
  const cards = useRunCards(selectedBoardId, selectedRunId);
  const card = cards.find((c) => c.id === activeCardId) ?? null;

  const { output, streaming } = useCardWs(activeCardId, card?.output ?? null);
  const { data: feedbackList = [] } = useFeedback(activeCardId);
  const { data: slides = [] } = useCardSlides(activeCardId);
  const { mutate: addFeedback, isPending: addingFeedback } = useAddFeedback();
  const { mutate: approve } = useApproveCard();
  const { mutate: askAgent } = useAskAgent();

  const [showRerun, setShowRerun] = useState(false);
  const [rerunNote, setRerunNote] = useState("");
  const [showNewThread, setShowNewThread] = useState(false);
  const [newThreadText, setNewThreadText] = useState("");
  const [directAnswer, setDirectAnswer] = useState("");
  const [showDirectAnswer, setShowDirectAnswer] = useState(false);
  const [askingIds, setAskingIds] = useState<Set<number>>(new Set());
  const [artifactRunning, setArtifactRunning] = useState(false);
  const [artifactPid, setArtifactPid] = useState<number | null>(null);
  const [artifactPort, setArtifactPort] = useState<number | null>(null);
  const [envReady, setEnvReady] = useState(true);
  const [slideIndex, setSlideIndex] = useState(0);

  useEffect(() => {
    if (!activeCardId || !card?.artifact_type) {
      setArtifactRunning(false); setArtifactPid(null); setArtifactPort(null);
      return;
    }
    fetch(`/api/cards/${activeCardId}/run-status`)
      .then((r) => r.json())
      .then((d) => {
        setArtifactRunning(d.running);
        setArtifactPid(d.pid ?? null);
        setArtifactPort(d.port ?? null);
      })
      .catch(() => {});
  }, [activeCardId, card?.artifact_type]);

  const handleRunArtifact = async () => {
    if (!activeCardId) return;
    const res = await fetch(`/api/cards/${activeCardId}/run`, { method: "POST" });
    const data = await res.json();
    if (data.pid) { setArtifactRunning(true); setArtifactPid(data.pid); }
    if (data.port) setArtifactPort(data.port);
  };

  const handleStopArtifact = async () => {
    if (!activeCardId) return;
    await fetch(`/api/cards/${activeCardId}/stop`, { method: "POST" });
    setArtifactRunning(false);
    setArtifactPid(null);
    setArtifactPort(null);
  };

  const handleApprove = () => approve({ cardId: activeCardId!, action: "approve" });
  const handleReject = () => approve({ cardId: activeCardId!, action: "reject" });

  const handleRerun = () => {
    addFeedback({ cardId: activeCardId!, type: "rerun", content: rerunNote });
    setRerunNote("");
    setShowRerun(false);
  };

  const handleDirectAnswer = () => {
    if (!directAnswer.trim()) return;
    addFeedback({ cardId: activeCardId!, type: "rerun", content: directAnswer.trim() });
    setDirectAnswer("");
    setShowDirectAnswer(false);
  };

  const handleNewThread = () => {
    if (!newThreadText.trim()) return;
    addFeedback({ cardId: activeCardId!, type: "comment", content: newThreadText.trim() });
    setNewThreadText("");
    setShowNewThread(false);
  };

  const handleAskAgent = (feedbackId: number) => {
    setAskingIds((prev) => new Set(prev).add(feedbackId));
    askAgent(feedbackId, {
      onError: () => setAskingIds((prev) => { const s = new Set(prev); s.delete(feedbackId); return s; }),
    });
  };

  const answeredParentIds = new Set(feedbackList.filter((f) => f.type === "agent_reply").map((f) => f.parent_id));
  const effectiveAskingIds = new Set([...askingIds].filter((id) => !answeredParentIds.has(id)));

  const snapshotItems = feedbackList.filter((f) => !f.parent_id && f.type === "output_snapshot");
  const snapshotIds = snapshotItems.map((f) => f.id);

  // 최상위 코멘트/재실행 스레드
  const threadRoots = feedbackList.filter(
    (f) => !f.parent_id && (f.type === "comment" || f.type === "rerun")
  );

  const getChildren = (parentId: number) =>
    feedbackList.filter((f) => f.parent_id === parentId).sort((a, b) => a.id - b.id);

  return (
    <Dialog
      open={!!activeCardId && !!card}
      onClose={() => setActiveCard(null)}
      title={card?.title ?? ""}
      className="max-w-2xl max-h-[90vh] flex flex-col"
    >
      {card && (
        <div className="flex flex-col overflow-hidden" style={{ maxHeight: "calc(90vh - 57px)" }}>
          <div className="flex-1 overflow-y-auto p-5 space-y-5">

            {/* 메타 */}
            <div className="flex items-center gap-2 flex-wrap">
              {card.agent_role && (
                <Badge variant="secondary" className="text-[10px]">{card.agent_role}</Badge>
              )}
              <StatusBadge status={card.status} />
              {card.design_system && (
                <div className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md bg-violet-50 text-violet-600 border border-violet-100">
                  <Palette size={9} />
                  {card.design_system}
                </div>
              )}
              {streaming && (
                <div className="flex items-center gap-1 text-[10px] text-blue-500">
                  <Loader2 size={10} className="animate-spin" />스트리밍 중...
                </div>
              )}
            </div>

            {/* 설명 */}
            {card.description && card.description.trim() !== card.title.trim() && (
              <p className="text-xs text-gray-500 leading-relaxed border-l-2 border-gray-200 pl-3">
                {card.description}
              </p>
            )}

            {/* 특수 카드 타입 */}
            {card?.card_kind === "clarification" && selectedBoardId && (
              <ClarificationCard card={card} boardId={selectedBoardId} />
            )}
            {card?.card_kind === "env_input" && selectedBoardId && (
              <EnvInputCard card={card} boardId={selectedBoardId} />
            )}

            {/* 일반 출력 결과 */}
            {card?.card_kind !== "clarification" && card?.card_kind !== "env_input" && (
              <>
                {output ? (
                  <div className="prose-output border border-gray-200 rounded-xl p-4 bg-white">
                    <ReactMarkdown>{output}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="flex items-center justify-center h-24 border border-dashed border-gray-200 rounded-xl bg-white">
                    <p className="text-xs text-gray-500">
                      {card.status === "backlog" ? "대기 중..." : "출력 없음"}
                    </p>
                  </div>
                )}
              </>
            )}

            {/* 질문 감지 */}
            {!streaming && output && hasUnansweredQuestions(output) && (
              <div className="border border-amber-200 rounded-xl overflow-hidden bg-amber-50">
                <div className="flex items-center justify-between px-3 py-2.5 border-b border-amber-200">
                  <div className="flex items-center gap-2">
                    <HelpCircle size={12} className="text-amber-500" />
                    <span className="text-[11px] font-medium text-amber-700">
                      에이전트가 답변을 기다리고 있어요
                    </span>
                  </div>
                  <button
                    onClick={() => setShowDirectAnswer((v) => !v)}
                    className="text-[10px] px-2 py-1 rounded-md bg-amber-100 text-amber-700 hover:bg-amber-200 transition-colors font-medium"
                  >
                    {showDirectAnswer ? "닫기" : "직접 답변하기"}
                  </button>
                </div>
                {showDirectAnswer && (
                  <div className="p-3 space-y-2">
                    <Textarea
                      value={directAnswer}
                      onChange={(e) => setDirectAnswer(e.target.value)}
                      placeholder="질문에 대한 답변을 입력하세요..."
                      rows={3}
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleDirectAnswer();
                        if (e.key === "Escape") setShowDirectAnswer(false);
                      }}
                    />
                    <div className="flex gap-2">
                      <Button size="sm" onClick={handleDirectAnswer} disabled={!directAnswer.trim() || addingFeedback}>
                        <Send size={12} /> 답변하고 재실행
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setShowDirectAnswer(false)}>취소</Button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 인스타 슬라이드 */}
            {slides.length > 0 && (
              <div className="border border-gray-200 rounded-xl overflow-hidden bg-white">
                <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-200">
                  <div className="flex items-center gap-1.5 text-[11px] font-medium text-gray-500">
                    <Images size={12} />
                    슬라이드 {slideIndex + 1} / {slides.length}
                  </div>
                  <div className="flex items-center gap-1">
                    <button onClick={() => setSlideIndex((i) => Math.max(0, i - 1))} disabled={slideIndex === 0}
                      className="p-1 rounded hover:bg-gray-100 disabled:opacity-30 transition-colors">
                      <ChevronLeft size={14} />
                    </button>
                    <button onClick={() => setSlideIndex((i) => Math.min(slides.length - 1, i + 1))} disabled={slideIndex === slides.length - 1}
                      className="p-1 rounded hover:bg-gray-100 disabled:opacity-30 transition-colors">
                      <ChevronRight size={14} />
                    </button>
                  </div>
                </div>
                <div className="aspect-square w-full bg-gray-100">
                  <img key={slides[slideIndex].url} src={slides[slideIndex].url} alt={`Slide ${slideIndex + 1}`} className="w-full h-full object-contain" />
                </div>
                {slides.length > 1 && (
                  <div className="flex gap-1 p-2 overflow-x-auto">
                    {slides.map((s, i) => (
                      <button key={s.filename} onClick={() => setSlideIndex(i)}
                        className={cn("shrink-0 w-12 h-12 rounded overflow-hidden border-2 transition-colors",
                          i === slideIndex ? "border-indigo-500" : "border-transparent opacity-60 hover:opacity-100")}>
                        <img src={s.url} alt={`thumb ${i + 1}`} className="w-full h-full object-cover" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 산출물 실행 */}
            {card.artifact_type && card.status === "done" && (
              <div className="border border-gray-200 rounded-xl p-3 bg-white space-y-2">
                {/* 환경 변수 폼 (C-5: card-drawer에도 동일한 가드 적용) */}
                {activeCardId && (
                  <ArtifactEnvForm cardId={activeCardId} onReadyChange={setEnvReady} />
                )}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className={cn("w-2 h-2 rounded-full", artifactRunning ? "bg-green-400 animate-pulse" : "bg-gray-300")} />
                    <span className="text-[11px] font-medium text-gray-900">
                      {card.artifact_type === "server" ? "서버" : "스크립트"}
                    </span>
                    {artifactPort && artifactRunning && (
                      <a href={`http://localhost:${artifactPort}`} target="_blank" rel="noreferrer"
                        className="flex items-center gap-0.5 text-[10px] text-indigo-500 hover:text-indigo-600">
                        :{artifactPort} <ExternalLink size={9} />
                      </a>
                    )}
                    {artifactPid && <span className="text-[9px] text-gray-500">PID {artifactPid}</span>}
                  </div>
                  <div className="flex gap-1.5">
                    {artifactRunning ? (
                      <Button size="sm" variant="destructive" onClick={handleStopArtifact} className="h-6 px-2 text-[10px]">
                        <Square size={10} /> 중지
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        onClick={handleRunArtifact}
                        disabled={!envReady}
                        title={!envReady ? "환경 변수를 먼저 설정해주세요" : undefined}
                        className="h-6 px-2 text-[10px]"
                      >
                        <Play size={10} />
                        {card.artifact_type === "server" ? "서버 실행하기" : "실행하기"}
                      </Button>
                    )}
                  </div>
                </div>
                <p className="text-[9px] text-gray-500 font-mono truncate">{card.run_command}</p>
              </div>
            )}

            {/* 승인/거절 */}
            {card.status === "awaiting_approval" && (
              <div className="flex gap-2">
                <Button size="sm" onClick={handleApprove} className="flex-1"><ThumbsUp size={13} /> 승인</Button>
                <Button size="sm" variant="destructive" onClick={handleReject} className="flex-1"><ThumbsDown size={13} /> 거절</Button>
              </div>
            )}

            {/* 재실행 */}
            <div>
              <Button size="sm" variant="outline" onClick={() => setShowRerun((v) => !v)}>
                <RotateCcw size={12} /> 재실행
              </Button>
              {showRerun && (
                <div className="mt-2 space-y-2 border border-gray-200 rounded-xl p-3 bg-white">
                  <p className="text-[11px] text-gray-500">
                    추가 요구사항이 있으면 입력하세요. 없으면 비워두고 재실행하세요.
                  </p>
                  <Textarea
                    value={rerunNote}
                    onChange={(e) => setRerunNote(e.target.value)}
                    placeholder="예: 한국어로 / 더 상세하게 / 톤을 바꿔줘..."
                    rows={2}
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={handleRerun} disabled={addingFeedback}>
                      <RotateCcw size={12} /> 재실행
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setShowRerun(false)}>취소</Button>
                  </div>
                </div>
              )}
            </div>

            {/* 이전 실행 스냅샷 */}
            {snapshotItems.length > 0 && (
              <div className="space-y-2">
                <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                  이전 실행 결과
                </p>
                {snapshotItems.map((f) => (
                  <OutputSnapshot key={f.id} feedback={f} runIndex={snapshotIds.indexOf(f.id) + 1} />
                ))}
              </div>
            )}

            {/* 대화 스레드 */}
            {threadRoots.length > 0 && (
              <div className="space-y-3">
                <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                  대화
                </p>
                {threadRoots.map((root) => (
                  <ThreadCard
                    key={root.id}
                    root={root}
                    getChildren={getChildren}
                    onAskAgent={handleAskAgent}
                    onReply={(parentId, content) =>
                      addFeedback({ cardId: activeCardId!, type: "comment", content, parentId })
                    }
                    effectiveAskingIds={effectiveAskingIds}
                    addingFeedback={addingFeedback}
                  />
                ))}
              </div>
            )}

            {/* 새 스레드 시작 */}
            {showNewThread ? (
              <div className="border border-gray-200 rounded-xl overflow-hidden bg-white">
                <div className="px-3 py-2.5 border-b border-gray-200 bg-gray-100">
                  <span className="text-[11px] font-medium text-gray-500">새 질문</span>
                </div>
                <div className="p-3 space-y-2">
                  <textarea
                    value={newThreadText}
                    onChange={(e) => setNewThreadText(e.target.value)}
                    placeholder="무엇이든 물어보세요..."
                    rows={3}
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleNewThread();
                      if (e.key === "Escape") setShowNewThread(false);
                    }}
                    className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 resize-none outline-none focus:border-indigo-400 text-gray-900 placeholder:text-gray-500 bg-white"
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={handleNewThread} disabled={!newThreadText.trim() || addingFeedback}>
                      <Send size={12} /> 보내기
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setShowNewThread(false)}>취소</Button>
                  </div>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowNewThread(true)}
                className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl border border-dashed border-gray-200 text-[11px] text-gray-500 hover:text-gray-900 hover:border-gray-400 hover:bg-white transition-colors"
              >
                <Plus size={12} />
                새 주제로 질문하기
              </button>
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}

/** 스레드 카드 — 기본 접힘, 클릭해서 펼침 */
function ThreadCard({
  root,
  getChildren,
  onAskAgent,
  onReply,
  effectiveAskingIds,
  addingFeedback,
}: {
  root: Feedback;
  getChildren: (id: number) => Feedback[];
  onAskAgent: (id: number) => void;
  onReply: (parentId: number, content: string) => void;
  effectiveAskingIds: Set<number>;
  addingFeedback: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [showReplyBox, setShowReplyBox] = useState(false);

  function flattenThread(node: Feedback): Feedback[] {
    const children = getChildren(node.id);
    return [node, ...children.flatMap(flattenThread)];
  }
  const messages = flattenThread(root);
  const lastMsg = messages[messages.length - 1];
  const lastIsAgent = lastMsg?.type === "agent_reply";
  const replyCount = messages.length - 1;

  const handleReplySubmit = () => {
    if (!replyText.trim()) return;
    onReply(lastMsg.id, replyText.trim());
    setReplyText("");
    setShowReplyBox(false);
  };

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm">
      {/* 스레드 헤더 — 항상 표시, 클릭해서 접기/펼치기 */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start gap-3 px-4 py-3 hover:bg-gray-50 transition-colors text-left"
      >
        <div className={cn("w-5 h-5 rounded-full flex items-center justify-center shrink-0 mt-0.5",
          root.author === "auto" ? "bg-gray-100" : "bg-indigo-100")}>
          {root.author === "auto"
            ? <Bot size={10} className="text-gray-500" />
            : <User size={10} className="text-indigo-600" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className={cn("text-[10px] font-semibold", root.author === "auto" ? "text-gray-500" : "text-indigo-600")}>
              {root.author === "auto" ? "자동 답변" : "나"}
            </span>
            {root.type === "rerun" && root.author !== "auto" && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">재실행 요청</span>
            )}
            {root.type === "rerun" && root.author === "auto" && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500 font-medium">자동 재실행</span>
            )}
            <span className="text-[9px] text-gray-400 ml-auto">
              {new Date(root.created_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}
            </span>
          </div>
          <p className="text-xs text-gray-700 line-clamp-1">{root.content}</p>
          {replyCount > 0 && (
            <p className="text-[10px] text-gray-400 mt-0.5">
              {replyCount}개 답변 {expanded ? "▲" : "▼"}
            </p>
          )}
        </div>
        {replyCount === 0 && (
          <ChevronDown size={13} className={cn("text-gray-400 shrink-0 mt-1 transition-transform", expanded && "rotate-180")} />
        )}
      </button>

      {/* 펼쳐진 메시지 목록 */}
      {expanded && (
        <>
          {messages.map((msg, idx) => {
            const isAgent = msg.type === "agent_reply";
            const isAsking = effectiveAskingIds.has(msg.id);
            const hasAnswer = getChildren(msg.id).some((c) => c.type === "agent_reply");

            return (
              <div
                key={msg.id}
                className={cn(
                  "px-4 py-3 border-t border-gray-100",
                  isAgent ? "bg-emerald-50" : "bg-white"
                )}
              >
                <div className="flex items-center gap-1.5 mb-1.5">
                  <div className={cn(
                    "w-5 h-5 rounded-full flex items-center justify-center shrink-0",
                    isAgent ? "bg-emerald-200" : "bg-indigo-100"
                  )}>
                    {isAgent
                      ? <Bot size={10} className="text-emerald-700" />
                      : <User size={10} className="text-indigo-600" />}
                  </div>
                  <span className={cn("text-[10px] font-semibold", isAgent ? "text-emerald-700" : "text-indigo-600")}>
                    {isAgent ? (msg.author ?? "에이전트") : "나"}
                  </span>
                  <span className="text-[9px] text-gray-400 ml-auto">
                    {new Date(msg.created_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>

                <div className={cn("text-xs leading-relaxed text-gray-800", isAgent && "prose-output")}>
                  {isAgent ? <ReactMarkdown>{msg.content}</ReactMarkdown> : msg.content}
                </div>

                {!isAgent && msg.type === "comment" && !hasAnswer && (
                  <button
                    onClick={() => onAskAgent(msg.id)}
                    disabled={isAsking}
                    className="mt-2 flex items-center gap-1 text-[10px] text-gray-400 hover:text-emerald-600 transition-colors disabled:opacity-50"
                  >
                    {isAsking
                      ? <><Loader2 size={9} className="animate-spin" /> 답변 생성 중...</>
                      : <><Bot size={9} /> 에이전트에게 답변 요청</>}
                  </button>
                )}
              </div>
            );
          })}

          {/* 답변하기 */}
          {lastIsAgent && (
            <div className="border-t border-gray-100 bg-gray-50 px-4 py-2.5">
              {showReplyBox ? (
                <div className="space-y-2">
                  <textarea
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    placeholder="추가 질문을 입력하세요..."
                    rows={2}
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleReplySubmit();
                      if (e.key === "Escape") setShowReplyBox(false);
                    }}
                    className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 resize-none outline-none focus:border-indigo-400 text-gray-800 placeholder:text-gray-400 bg-white"
                  />
                  <div className="flex gap-1.5">
                    <button
                      onClick={handleReplySubmit}
                      disabled={!replyText.trim() || addingFeedback}
                      className="flex items-center gap-1 text-[10px] px-2.5 py-1 rounded-md bg-indigo-100 text-indigo-700 hover:bg-indigo-200 disabled:opacity-40 transition-colors font-medium"
                    >
                      <Send size={9} /> 전송
                    </button>
                    <button
                      onClick={() => setShowReplyBox(false)}
                      className="text-[10px] px-2 py-1 text-gray-500 hover:text-gray-800 transition-colors"
                    >
                      취소
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowReplyBox(true)}
                  className="flex items-center gap-1.5 text-[10px] text-gray-500 hover:text-indigo-600 transition-colors"
                >
                  <MessageSquare size={10} /> 이 스레드에 답변하기
                </button>
              )}
            </div>
          )}
        </>
      )}

      {/* 접힌 상태에서 답변 없는 코멘트 → 에이전트 답변 요청 버튼 */}
      {!expanded && messages.length === 1 && root.type === "comment" && (
        <div className="border-t border-gray-100 bg-gray-50 px-4 py-2.5">
          <button
            onClick={() => onAskAgent(root.id)}
            disabled={effectiveAskingIds.has(root.id)}
            className="flex items-center gap-1.5 text-[10px] text-gray-500 hover:text-emerald-600 transition-colors disabled:opacity-50"
          >
            {effectiveAskingIds.has(root.id)
              ? <><Loader2 size={9} className="animate-spin" /> 답변 생성 중...</>
              : <><Bot size={9} /> 에이전트에게 답변 요청</>}
          </button>
        </div>
      )}
    </div>
  );
}

function OutputSnapshot({ feedback, runIndex }: { feedback: Feedback; runIndex: number }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-gray-100 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <History size={11} className="text-gray-500" />
          <span className="text-[11px] font-medium text-gray-900">
            {runIndex}번째 실행 결과
          </span>
          <span className="text-[10px] text-gray-500">
            {new Date(feedback.created_at).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
          </span>
        </div>
        {expanded
          ? <ChevronUp size={12} className="text-gray-500" />
          : <ChevronDown size={12} className="text-gray-500" />}
      </button>
      {expanded && (
        <div className="prose-output px-4 py-3 text-xs border-t border-gray-200">
          <ReactMarkdown>{feedback.content}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; variant: "default" | "secondary" | "success" | "destructive" | "warning" }> = {
    done: { label: "완료", variant: "success" },
    error: { label: "오류", variant: "destructive" },
    in_progress: { label: "진행 중", variant: "default" },
    awaiting_approval: { label: "승인 대기", variant: "warning" },
    rejected: { label: "거절됨", variant: "destructive" },
    backlog: { label: "대기", variant: "secondary" },
  };
  const cfg = map[status] ?? { label: status, variant: "secondary" as const };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}
