import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { MessageCircle, Send } from "lucide-react";
import type { Card } from "@/api/client";

interface Question {
  id: string;
  question: string;
}

export function ClarificationCard({
  card,
  boardId,
}: {
  card: Card;
  boardId: number;
}) {
  const questions: Question[] = (() => {
    try {
      return JSON.parse(card.output || "[]");
    } catch {
      return [];
    }
  })();

  const [answers, setAnswers] = useState<Record<string, string>>({});
  const qc = useQueryClient();

  const { mutate: submit, isPending } = useMutation({
    mutationFn: () =>
      api(`/api/boards/${boardId}/clarification`, {
        method: "POST",
        body: JSON.stringify({ answers }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["board", boardId] }),
  });

  if (card.status === "done") return null;

  const allAnswered = questions.every((q) => answers[q.id]?.trim());

  return (
    <div className="border border-amber-200 bg-amber-50 rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-2">
        <MessageCircle size={14} className="text-amber-600" />
        <span className="text-[13px] font-semibold text-amber-800">
          추가 정보가 필요합니다
        </span>
      </div>
      <div className="space-y-3">
        {questions.map((q) => (
          <div key={q.id}>
            <label className="text-[12px] text-gray-700 mb-1 block font-medium">
              {q.question}
            </label>
            <textarea
              className="w-full text-[12px] border border-gray-200 rounded-md p-2 resize-none focus:outline-none focus:ring-1 focus:ring-amber-400"
              rows={2}
              value={answers[q.id] || ""}
              onChange={(e) =>
                setAnswers((p) => ({ ...p, [q.id]: e.target.value }))
              }
              placeholder="답변을 입력하세요..."
            />
          </div>
        ))}
      </div>
      <Button
        size="sm"
        onClick={() => submit()}
        disabled={isPending || !allAnswered}
        className="w-full"
      >
        <Send size={12} />
        {isPending ? "제출 중..." : "답변 제출하고 계속 진행"}
      </Button>
    </div>
  );
}
