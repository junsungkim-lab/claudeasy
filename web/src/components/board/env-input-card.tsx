import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { KeyRound, Save } from "lucide-react";
import type { Card } from "@/api/client";

interface EnvVar {
  key: string;
  description: string;
}

export function EnvInputCard({
  card,
  boardId,
}: {
  card: Card;
  boardId: number;
}) {
  const envVars: EnvVar[] = (() => {
    try {
      return JSON.parse(card.output || "[]");
    } catch {
      return [];
    }
  })();

  const [values, setValues] = useState<Record<string, string>>({});
  const qc = useQueryClient();

  const { mutate: save, isPending } = useMutation({
    mutationFn: () =>
      api(`/api/boards/${boardId}/env`, {
        method: "POST",
        body: JSON.stringify(values),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["board", boardId] }),
  });

  if (card.status === "done") return null;

  const isSecret = (key: string) =>
    /pass|pw|password|secret|token|key/i.test(key);

  const allFilled = envVars.every((v) => values[v.key]?.trim());

  return (
    <div className="border border-indigo-200 bg-indigo-50 rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-2">
        <KeyRound size={14} className="text-indigo-600" />
        <span className="text-[13px] font-semibold text-indigo-800">
          환경 변수 설정
        </span>
      </div>
      <div className="space-y-2">
        {envVars.map((v) => (
          <div key={v.key}>
            <label className="text-[11px] text-gray-600 mb-0.5 block">
              <span className="font-mono font-semibold">{v.key}</span>
              {v.description && (
                <span className="ml-1 text-gray-400">— {v.description}</span>
              )}
            </label>
            <Input
              type={isSecret(v.key) ? "password" : "text"}
              placeholder={v.key}
              value={values[v.key] || ""}
              onChange={(e) =>
                setValues((p) => ({ ...p, [v.key]: e.target.value }))
              }
              className="text-xs h-8 font-mono"
            />
          </div>
        ))}
      </div>
      <Button
        size="sm"
        onClick={() => save()}
        disabled={isPending || !allFilled}
        className="w-full"
      >
        <Save size={12} />
        {isPending ? "저장 중..." : "저장하고 계속"}
      </Button>
    </div>
  );
}
