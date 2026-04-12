import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Feedback } from "@/api/client";

export interface SlideInfo {
  filename: string;
  url: string;
}

export function useCardSlides(cardId: number | null) {
  return useQuery<SlideInfo[]>({
    queryKey: ["slides", cardId],
    queryFn: () => api(`/api/cards/${cardId}/slides`),
    enabled: !!cardId,
    refetchInterval: false,
  });
}

export function useAskAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (feedbackId: number) =>
      api(`/api/feedback/${feedbackId}/ask`, { method: "POST" }),
    onSuccess: () => {
      // 답변 생성은 비동기라 잠시 후 폴링으로 반영
      setTimeout(() => qc.invalidateQueries({ queryKey: ["feedback"] }), 1500);
      setTimeout(() => qc.invalidateQueries({ queryKey: ["feedback"] }), 4000);
    },
  });
}

export function useFeedback(cardId: number | null) {
  return useQuery<Feedback[]>({
    queryKey: ["feedback", cardId],
    queryFn: () => api(`/api/cards/${cardId}/feedback`),
    enabled: !!cardId,
  });
}

export function useAddFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      cardId,
      type,
      content,
      parentId,
    }: {
      cardId: number;
      type: string;
      content?: string;
      parentId?: number;
    }) =>
      api(`/api/cards/${cardId}/feedback`, {
        method: "POST",
        body: JSON.stringify({ type, content, parent_id: parentId }),
      }),
    onSuccess: (_, { cardId }) => {
      qc.invalidateQueries({ queryKey: ["feedback", cardId] });
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function useApproveCard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      cardId,
      action,
      message,
    }: {
      cardId: number;
      action: "approve" | "reject";
      message?: string;
    }) =>
      api(`/api/cards/${cardId}/approve`, {
        method: "POST",
        body: JSON.stringify({ action, message }),
      }),
    onSuccess: (_, { cardId }) => {
      qc.invalidateQueries({ queryKey: ["feedback", cardId] });
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}
