import { useState, useEffect } from "react";
import { KeyRound, Save, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface EnvVar {
  key: string;
  description: string;
  has_value: boolean;
  from_env?: boolean;
}

export interface ArtifactEnvFormProps {
  cardId: number;
  onSaved?: () => void;
  /** 미설정 변수가 있을 때 실행 차단 여부를 외부에 알림 */
  onReadyChange?: (ready: boolean) => void;
}

export function ArtifactEnvForm({ cardId, onSaved, onReadyChange }: ArtifactEnvFormProps) {
  const [vars, setVars] = useState<EnvVar[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    fetch(`/api/cards/${cardId}/env-vars`)
      .then((r) => r.json())
      .then((d) => {
        if (d.vars?.length) {
          setVars(d.vars);
          const hasUnset = d.vars.some((v: EnvVar) => !v.has_value);
          setOpen(hasUnset);
          onReadyChange?.(!hasUnset);
        } else {
          onReadyChange?.(true);
        }
      })
      .catch(() => { onReadyChange?.(true); });
  }, [cardId]);

  if (!vars.length) return null;

  const missingCount = vars.filter((v) => !v.has_value && !values[v.key]?.trim()).length;
  const isSecret = (key: string) => /pass|pw|password|secret|token|key/i.test(key);

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetch(`/api/cards/${cardId}/env`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      setVars((prev) => prev.map((v) => values[v.key] ? { ...v, has_value: true } : v));
      setValues({});
      setOpen(false);
      onReadyChange?.(true);
      onSaved?.();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-indigo-200 rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-3 py-2 bg-indigo-50 hover:bg-indigo-100 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <KeyRound size={12} className="text-indigo-600" />
          <span className="text-[11px] font-semibold text-indigo-800">환경 변수</span>
          {missingCount > 0 ? (
            <span className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">
              {missingCount}개 미설정
            </span>
          ) : (
            <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-full font-medium">
              설정 완료
            </span>
          )}
        </div>
        {open ? <ChevronUp size={12} className="text-indigo-500" /> : <ChevronDown size={12} className="text-indigo-500" />}
      </button>

      {open && (
        <div className="p-3 bg-white space-y-2">
          {vars.map((v) => (
            <div key={v.key}>
              <label className="flex items-center gap-1.5 text-[11px] text-gray-600 mb-1">
                <span className="font-mono font-semibold">{v.key}</span>
                {v.from_env && !values[v.key] && (
                  <span className="text-[10px] text-blue-500">시스템 환경변수 (저장 시 .env 우선)</span>
                )}
                {v.has_value && !v.from_env && !values[v.key] && (
                  <span className="text-[10px] text-emerald-600">✓ 저장됨</span>
                )}
              </label>
              <Input
                type={isSecret(v.key) ? "password" : "text"}
                placeholder={v.has_value ? "변경하려면 입력" : v.key}
                value={values[v.key] || ""}
                onChange={(e) => setValues((p) => ({ ...p, [v.key]: e.target.value }))}
                className="text-xs h-8 font-mono"
              />
            </div>
          ))}
          <Button
            size="sm"
            onClick={handleSave}
            disabled={saving || !Object.keys(values).length}
            className="w-full mt-1 h-7 text-[11px]"
          >
            <Save size={11} />
            {saving ? "저장 중..." : missingCount === 0 ? "저장" : "입력한 값만 저장"}
          </Button>
        </div>
      )}
    </div>
  );
}
