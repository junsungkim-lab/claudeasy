import { useState } from "react";
import { Save, Send, Check, X } from "lucide-react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface NotifyConfig {
  telegram_token: string;
  telegram_chat_id: string;
  email_host: string;
  email_port: number;
  email_user: string;
  email_pass: string;
  email_to: string;
}

export function SettingsPage() {
  return (
    <div className="flex-1 overflow-y-auto bg-gray-50 p-8">
      <div className="max-w-xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <button
            onClick={() => window.history.back()}
            className="text-gray-400 hover:text-gray-700 transition-colors"
            title="뒤로"
          >
            ←
          </button>
          <h1 className="text-lg font-semibold text-gray-900">설정</h1>
        </div>
        <NotificationSettings />
      </div>
    </div>
  );
}

function NotificationSettings() {
  const { data, isLoading } = useQuery<NotifyConfig>({
    queryKey: ["notify-settings"],
    queryFn: () => api("/api/settings/notifications"),
  });

  const [form, setForm] = useState<Partial<NotifyConfig>>({});
  const [testResult, setTestResult] = useState<"idle" | "ok" | "fail">("idle");

  const merged: NotifyConfig = {
    telegram_token: "",
    telegram_chat_id: "",
    email_host: "",
    email_port: 587,
    email_user: "",
    email_pass: "",
    email_to: "",
    ...data,
    ...form,
  };

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: (body: Partial<NotifyConfig>) =>
      api("/api/settings/notifications", { method: "PUT", body: JSON.stringify(body) }),
  });

  const { mutate: testTelegram, isPending: testing } = useMutation({
    mutationFn: () =>
      api<{ ok: boolean }>("/api/settings/notifications/test-telegram", {
        method: "POST",
        body: JSON.stringify({
          token: merged.telegram_token,
          chat_id: merged.telegram_chat_id,
        }),
      }),
    onSuccess: (res) => setTestResult(res.ok ? "ok" : "fail"),
    onError: () => setTestResult("fail"),
  });

  const set = (k: keyof NotifyConfig, v: string | number) =>
    setForm((p) => ({ ...p, [k]: v }));

  if (isLoading) return <p className="text-sm text-gray-500">로딩 중...</p>;

  return (
    <div className="space-y-6">
      {/* 텔레그램 */}
      <section className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <div>
          <h2 className="text-[13px] font-semibold text-gray-900">텔레그램</h2>
          <p className="text-[11px] text-gray-500 mt-0.5">
            스케줄 실행 결과를 텔레그램으로 받습니다.{" "}
            <a
              href="https://t.me/BotFather"
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-500 hover:underline"
            >
              @BotFather
            </a>
            에서 Bot Token을 발급받으세요.
          </p>
        </div>
        <div className="space-y-2">
          <div>
            <label className="text-[11px] text-gray-500 mb-1 block">Bot Token</label>
            <Input
              placeholder="1234567890:ABCdefGhIJKlmNoPQRsTUVwXyZ"
              value={merged.telegram_token}
              onChange={(e) => set("telegram_token", e.target.value)}
              className="text-xs h-8"
            />
          </div>
          <div>
            <label className="text-[11px] text-gray-500 mb-1 block">Chat ID</label>
            <Input
              placeholder="-1001234567890"
              value={merged.telegram_chat_id}
              onChange={(e) => set("telegram_chat_id", e.target.value)}
              className="text-xs h-8"
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => { setTestResult("idle"); testTelegram(); }}
            disabled={testing || !merged.telegram_token || !merged.telegram_chat_id}
          >
            <Send size={12} />
            {testing ? "전송 중..." : "테스트 전송"}
          </Button>
          {testResult === "ok" && (
            <span className="flex items-center gap-1 text-[11px] text-emerald-600">
              <Check size={11} /> 전송 성공
            </span>
          )}
          {testResult === "fail" && (
            <span className="flex items-center gap-1 text-[11px] text-red-500">
              <X size={11} /> 전송 실패
            </span>
          )}
        </div>
      </section>

      {/* 이메일 */}
      <section className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <div>
          <h2 className="text-[13px] font-semibold text-gray-900">이메일 (SMTP)</h2>
          <p className="text-[11px] text-gray-500 mt-0.5">
            Gmail 사용 시 앱 비밀번호를 발급해 사용하세요.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="col-span-2 sm:col-span-1">
            <label className="text-[11px] text-gray-500 mb-1 block">SMTP Host</label>
            <Input
              placeholder="smtp.gmail.com"
              value={merged.email_host}
              onChange={(e) => set("email_host", e.target.value)}
              className="text-xs h-8"
            />
          </div>
          <div>
            <label className="text-[11px] text-gray-500 mb-1 block">Port</label>
            <Input
              placeholder="587"
              value={merged.email_port}
              onChange={(e) => set("email_port", Number(e.target.value))}
              className="text-xs h-8"
              type="number"
            />
          </div>
          <div>
            <label className="text-[11px] text-gray-500 mb-1 block">계정 (발신)</label>
            <Input
              placeholder="you@gmail.com"
              value={merged.email_user}
              onChange={(e) => set("email_user", e.target.value)}
              className="text-xs h-8"
            />
          </div>
          <div>
            <label className="text-[11px] text-gray-500 mb-1 block">비밀번호 (앱 비밀번호)</label>
            <Input
              placeholder="••••••••••••"
              type="password"
              value={merged.email_pass}
              onChange={(e) => set("email_pass", e.target.value)}
              className="text-xs h-8"
            />
          </div>
          <div className="col-span-2">
            <label className="text-[11px] text-gray-500 mb-1 block">수신 이메일</label>
            <Input
              placeholder="receive@example.com"
              value={merged.email_to}
              onChange={(e) => set("email_to", e.target.value)}
              className="text-xs h-8"
            />
          </div>
        </div>
      </section>

      <Button
        onClick={() => save(merged)}
        disabled={saving}
        className="w-full"
      >
        <Save size={13} />
        {saving ? "저장 중..." : "설정 저장"}
      </Button>
    </div>
  );
}
