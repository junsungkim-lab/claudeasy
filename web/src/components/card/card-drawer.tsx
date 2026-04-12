import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { ThumbsUp, ThumbsDown, RotateCcw, Loader2, MessageSquare, Bot, User, Send, ChevronLeft, ChevronRight, Images, ChevronDown, ChevronUp, History, HelpCircle } from "lucide-react";

/** 서버의 has_unanswered_questions와 동일한 휴리스틱 */
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

  const [rerunNote, setRerunNote] = useState("");
  const [showRerun, setShowRerun] = useState(false);
  const [comment, setComment] = useState("");
  const [showComment, setShowComment] = useState(false);
  const [slideIndex, setSlideIndex] = useState(0);
  const [directAnswer, setDirectAnswer] = useState("");
  const [showDirectAnswer, setShowDirectAnswer] = useState(false);
  // 답변 요청 중인 feedbackId Set — WS로 feedback_update 오면 자동 해제
  const [askingIds, setAskingIds] = useState<Set<number>>(new Set());

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

  const handleComment = () => {
    if (!comment.trim()) return;
    addFeedback({ cardId: activeCardId!, type: "comment", content: comment });
    setComment("");
    setShowComment(false);
  };

  const handleAskAgent = (feedbackId: number) => {
    setAskingIds((prev) => new Set(prev).add(feedbackId));
    askAgent(feedbackId, {
      onError: () => setAskingIds((prev) => { const s = new Set(prev); s.delete(feedbackId); return s; }),
    });
  };

  // feedbackList에 이미 답변(agent_reply)이 있으면 askingIds에서 제거
  const answeredParentIds = new Set(feedbackList.filter((f) => f.type === "agent_reply").map((f) => f.parent_id));
  const effectiveAskingIds = new Set([...askingIds].filter((id) => !answeredParentIds.has(id)));

  // 재실행 타임라인 아이템 (스냅샷 + 재실행 노트 포함, 최상위만)
  const timelineItems = feedbackList.filter(
    (f) => !f.parent_id && (f.type === "comment" || f.type === "rerun" || f.type === "approve" || f.type === "reject" || f.type === "output_snapshot")
  );

  // 이전 실행 결과(스냅샷) 개수 — 라벨링용
  const snapshotIds = feedbackList.filter((f) => f.type === "output_snapshot").map((f) => f.id);

  // 최상위 코멘트만 (parent_id === null)
  const topLevel = timelineItems;

  // 특정 부모의 자식 전체 (모든 깊이)
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
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {/* Meta */}
            <div className="flex items-center gap-2 flex-wrap">
              {card.agent_role && (
                <Badge variant="secondary" className="text-[10px]">{card.agent_role}</Badge>
              )}
              <StatusBadge status={card.status} />
              {streaming && (
                <div className="flex items-center gap-1 text-[10px] text-blue-400">
                  <Loader2 size={10} className="animate-spin" />스트리밍 중...
                </div>
              )}
            </div>

            {/* Description — 제목과 다를 때만 표시 */}
            {card.description && card.description.trim() !== card.title.trim() && (
              <p className="text-xs text-[--color-muted-foreground] leading-relaxed border-l-2 border-[--color-border] pl-3">
                {card.description}
              </p>
            )}

            {/* Output */}
            {output ? (
              <div className="prose-output border border-[--color-border] rounded-xl p-4 bg-[--color-background]">
                <ReactMarkdown>{output}</ReactMarkdown>
              </div>
            ) : (
              <div className="flex items-center justify-center h-24 border border-dashed border-[--color-border] rounded-xl">
                <p className="text-xs text-[--color-muted-foreground]">
                  {card.status === "backlog" ? "대기 중..." : "출력 없음"}
                </p>
              </div>
            )}

            {/* 질문 감지 시 직접 답변 UI */}
            {!streaming && output && hasUnansweredQuestions(output) && (
              <div className="border border-amber-800/40 rounded-xl overflow-hidden bg-amber-950/20">
                <div className="flex items-center justify-between px-3 py-2 border-b border-amber-800/30">
                  <div className="flex items-center gap-2">
                    <HelpCircle size={12} className="text-amber-400" />
                    <span className="text-[11px] font-medium text-amber-300">
                      에이전트가 답변을 기다리고 있어요
                    </span>
                  </div>
                  <button
                    onClick={() => setShowDirectAnswer((v) => !v)}
                    className="text-[10px] px-2 py-0.5 rounded bg-amber-900/40 text-amber-300 hover:bg-amber-900/60 transition-colors"
                  >
                    {showDirectAnswer ? "닫기" : "직접 답변하기"}
                  </button>
                </div>
                {showDirectAnswer && (
                  <div className="p-3 space-y-2">
                    <Textarea
                      value={directAnswer}
                      onChange={(e) => setDirectAnswer(e.target.value)}
                      placeholder="질문에 대한 답변을 입력하세요. 에이전트가 이 내용을 바탕으로 다시 실행합니다..."
                      rows={4}
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleDirectAnswer();
                        if (e.key === "Escape") setShowDirectAnswer(false);
                      }}
                    />
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={handleDirectAnswer}
                        disabled={!directAnswer.trim() || addingFeedback}
                      >
                        <Send size={12} /> 답변하고 재실행
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setShowDirectAnswer(false)}>
                        취소
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 인스타 슬라이드 미리보기 */}
            {slides.length > 0 && (
              <div className="border border-[--color-border] rounded-xl overflow-hidden bg-[--color-background]">
                <div className="flex items-center justify-between px-3 py-2 border-b border-[--color-border]">
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold text-[--color-muted-foreground]">
                    <Images size={12} />
                    슬라이드 {slideIndex + 1} / {slides.length}
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setSlideIndex((i) => Math.max(0, i - 1))}
                      disabled={slideIndex === 0}
                      className="p-1 rounded hover:bg-[--color-muted]/40 disabled:opacity-30 transition-colors"
                    >
                      <ChevronLeft size={14} />
                    </button>
                    <button
                      onClick={() => setSlideIndex((i) => Math.min(slides.length - 1, i + 1))}
                      disabled={slideIndex === slides.length - 1}
                      className="p-1 rounded hover:bg-[--color-muted]/40 disabled:opacity-30 transition-colors"
                    >
                      <ChevronRight size={14} />
                    </button>
                  </div>
                </div>
                <div className="aspect-square w-full bg-black">
                  <img
                    key={slides[slideIndex].url}
                    src={slides[slideIndex].url}
                    alt={`Slide ${slideIndex + 1}`}
                    className="w-full h-full object-contain"
                  />
                </div>
                {/* 썸네일 스트립 */}
                {slides.length > 1 && (
                  <div className="flex gap-1 p-2 overflow-x-auto">
                    {slides.map((s, i) => (
                      <button
                        key={s.filename}
                        onClick={() => setSlideIndex(i)}
                        className={cn(
                          "shrink-0 w-12 h-12 rounded overflow-hidden border-2 transition-colors",
                          i === slideIndex ? "border-indigo-500" : "border-transparent opacity-60 hover:opacity-100"
                        )}
                      >
                        <img src={s.url} alt={`thumb ${i + 1}`} className="w-full h-full object-cover" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 승인/거절 */}
            {card.status === "awaiting_approval" && (
              <div className="flex gap-2">
                <Button size="sm" onClick={handleApprove} className="flex-1">
                  <ThumbsUp size={13} /> 승인
                </Button>
                <Button size="sm" variant="destructive" onClick={handleReject} className="flex-1">
                  <ThumbsDown size={13} /> 거절
                </Button>
              </div>
            )}

            {/* 재실행 */}
            <div>
              <Button size="sm" variant="ghost" onClick={() => { setShowRerun(v => !v); setShowComment(false); }}>
                <RotateCcw size={13} /> 재실행
              </Button>
            </div>
            {showRerun && (
              <div className="space-y-2 border border-[--color-border] rounded-xl p-3 bg-[--color-muted]/20">
                <p className="text-[11px] text-[--color-muted-foreground]">
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

            {/* 실행 타임라인 (이전 결과 스냅샷 + 재실행 노트 + 코멘트) */}
            {topLevel.length > 0 && (
              <div className="space-y-3">
                <p className="text-[10px] font-semibold text-[--color-muted-foreground] uppercase tracking-wider">
                  실행 히스토리
                </p>
                {topLevel.map((f) =>
                  f.type === "output_snapshot" ? (
                    <OutputSnapshot
                      key={f.id}
                      feedback={f}
                      runIndex={snapshotIds.indexOf(f.id) + 1}
                    />
                  ) : (
                    <CommentThread
                      key={f.id}
                      comment={f}
                      getChildren={getChildren}
                      onAskAgent={handleAskAgent}
                      onReply={(parentId, content) =>
                        addFeedback({ cardId: activeCardId!, type: "comment", content, parentId })
                      }
                      effectiveAskingIds={effectiveAskingIds}
                      addingFeedback={addingFeedback}
                    />
                  )
                )}
              </div>
            )}
          </div>

          {/* 하단 코멘트 입력창 */}
          <div className="border-t border-[--color-border] p-4 shrink-0">
            {showComment ? (
              <div className="space-y-2">
                <Textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="코멘트를 남기세요..."
                  rows={2}
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleComment();
                    if (e.key === "Escape") setShowComment(false);
                  }}
                />
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleComment} disabled={!comment.trim() || addingFeedback}>
                    <Send size={12} /> 남기기
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowComment(false)}>취소</Button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => { setShowComment(true); setShowRerun(false); }}
                className="w-full text-left text-xs text-[--color-muted-foreground] hover:text-[--color-foreground] bg-[--color-muted]/30 hover:bg-[--color-muted]/50 rounded-lg px-3 py-2.5 transition-colors border border-[--color-border]"
              >
                <MessageSquare size={12} className="inline mr-2 opacity-60" />
                코멘트 남기기...
              </button>
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}

// 단일 메시지 버블 (재귀 트리에서 사용)
function MessageBubble({
  item,
  getChildren,
  onAskAgent,
  onReply,
  effectiveAskingIds,
  addingFeedback,
  depth = 0,
}: {
  item: Feedback;
  getChildren: (id: number) => Feedback[];
  onAskAgent: (id: number) => void;
  onReply: (parentId: number, content: string) => void;
  effectiveAskingIds: Set<number>;
  addingFeedback: boolean;
  depth?: number;
}) {
  const [replyText, setReplyText] = useState("");
  const [showReplyBox, setShowReplyBox] = useState(false);

  const isUser = item.author === "user" || !item.author;
  const isAgent = item.type === "agent_reply";
  const children = getChildren(item.id);
  const hasAnswer = children.some((c) => c.type === "agent_reply");
  const isAsking = effectiveAskingIds.has(item.id);

  const handleReplySubmit = () => {
    if (!replyText.trim()) return;
    onReply(item.id, replyText.trim());
    setReplyText("");
    setShowReplyBox(false);
  };

  return (
    <div className={cn("space-y-2", depth > 0 && "pl-6 border-l border-[--color-border]/40")}>
      {/* 말풍선 */}
      <div className={cn("flex gap-2.5", isUser ? "" : "flex-row-reverse")}>
        <div className={cn(
          "w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5",
          isUser ? "bg-indigo-900/60" : "bg-emerald-900/60"
        )}>
          {isUser
            ? <User size={11} className="text-indigo-300" />
            : <Bot size={11} className="text-emerald-300" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            <span className={cn("text-[10px] font-semibold", isAgent ? "text-emerald-400" : "text-[--color-muted-foreground]")}>
              {isUser ? "나" : item.author}
            </span>
            {item.type === "rerun" && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-900/40 text-amber-300">재실행</span>
            )}
            {isAgent && (
              <span className="text-[9px] text-[--color-muted-foreground]">답변</span>
            )}
          </div>
          <div className={cn(
            "rounded-xl px-3 py-2 text-xs leading-relaxed",
            isUser
              ? "bg-indigo-950/40 border border-indigo-800/30 text-[--color-foreground]"
              : "bg-emerald-950/40 border border-emerald-800/30 text-[--color-foreground] prose-output"
          )}>
            {isAgent ? <ReactMarkdown>{item.content}</ReactMarkdown> : item.content}
          </div>

          {/* 액션 버튼 영역 */}
          <div className="mt-1 flex items-center gap-3">
            {/* 유저 코멘트: 답변 아직 없으면 "에이전트에게 답변 요청" */}
            {isUser && item.type === "comment" && !hasAnswer && (
              <button
                onClick={() => onAskAgent(item.id)}
                disabled={isAsking}
                className="flex items-center gap-1 text-[10px] text-[--color-muted-foreground] hover:text-emerald-400 transition-colors disabled:opacity-50"
              >
                {isAsking
                  ? <><Loader2 size={9} className="animate-spin" /> 답변 생성 중...</>
                  : <><Bot size={9} /> 에이전트에게 답변 요청</>
                }
              </button>
            )}
            {/* 에이전트 답변: "답변하기" (재질문) */}
            {isAgent && (
              <button
                onClick={() => setShowReplyBox((v) => !v)}
                className="flex items-center gap-1 text-[10px] text-[--color-muted-foreground] hover:text-indigo-400 transition-colors"
              >
                <MessageSquare size={9} /> 답변하기
              </button>
            )}
          </div>

          {/* 재질문 입력창 */}
          {showReplyBox && (
            <div className="mt-2 space-y-1.5">
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
                className="w-full text-xs bg-[--color-muted]/20 border border-[--color-border] rounded-lg px-2.5 py-1.5 resize-none outline-none focus:border-indigo-500/50 text-[--color-foreground] placeholder:text-[--color-muted-foreground]"
              />
              <div className="flex gap-1.5">
                <button
                  onClick={handleReplySubmit}
                  disabled={!replyText.trim() || addingFeedback}
                  className="flex items-center gap-1 text-[10px] px-2.5 py-1 rounded-lg bg-indigo-900/40 text-indigo-300 hover:bg-indigo-900/60 disabled:opacity-40 transition-colors"
                >
                  <Send size={9} /> 전송
                </button>
                <button
                  onClick={() => setShowReplyBox(false)}
                  className="text-[10px] px-2 py-1 rounded-lg text-[--color-muted-foreground] hover:text-[--color-foreground] transition-colors"
                >
                  취소
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 자식 메시지 재귀 렌더링 */}
      {children.map((child) => (
        <MessageBubble
          key={child.id}
          item={child}
          getChildren={getChildren}
          onAskAgent={onAskAgent}
          onReply={onReply}
          effectiveAskingIds={effectiveAskingIds}
          addingFeedback={addingFeedback}
          depth={depth + 1}
        />
      ))}
    </div>
  );
}

function CommentThread({
  comment,
  getChildren,
  onAskAgent,
  onReply,
  effectiveAskingIds,
  addingFeedback,
}: {
  comment: Feedback;
  getChildren: (id: number) => Feedback[];
  onAskAgent: (id: number) => void;
  onReply: (parentId: number, content: string) => void;
  effectiveAskingIds: Set<number>;
  addingFeedback: boolean;
}) {
  return (
    <MessageBubble
      item={comment}
      getChildren={getChildren}
      onAskAgent={onAskAgent}
      onReply={onReply}
      effectiveAskingIds={effectiveAskingIds}
      addingFeedback={addingFeedback}
      depth={0}
    />
  );
}

// 이전 실행 결과 스냅샷 (접기/펼치기)
function OutputSnapshot({ feedback, runIndex }: { feedback: Feedback; runIndex: number }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="border border-[--color-border] rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 bg-[--color-muted]/20 hover:bg-[--color-muted]/30 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <History size={11} className="text-[--color-muted-foreground]" />
          <span className="text-[11px] font-medium text-[--color-muted-foreground]">
            {runIndex}번째 실행 결과
          </span>
          <span className="text-[10px] text-[--color-muted-foreground]/60">
            {new Date(feedback.created_at).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
          </span>
        </div>
        {expanded
          ? <ChevronUp size={12} className="text-[--color-muted-foreground]" />
          : <ChevronDown size={12} className="text-[--color-muted-foreground]" />}
      </button>
      {expanded && (
        <div className="prose-output p-4 text-xs border-t border-[--color-border] bg-[--color-background]">
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
