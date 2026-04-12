// 항상 상대 URL 사용 — DEV에서는 Vite proxy가 8100으로 포워드, PROD에서는 동일 오리진
const BASE = "";

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ""}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function wsUrl(path: string) {
  // DEV: Vite proxy (/ws → ws://localhost:8100) 경유, PROD: 동일 호스트
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${path}`;
}

// Types mirroring the FastAPI models

export interface Board {
  id: number;
  name: string;
  description: string;
  cron_expr: string | null;
  approval_mode: "auto" | "manual";
  project_path: string | null;
  status: string;
  created_at: string;
}

export interface Run {
  id: number;
  board_id: number;
  status: "generating" | "ready" | "running" | "done" | "error";
  session_id: string | null;
  trigger: "manual" | "cron" | "rerun";
  created_at: string;
  finished_at: string | null;
}

export interface Card {
  id: number;
  board_id: number;
  run_id: number;
  title: string;
  description: string;
  status: "backlog" | "awaiting_approval" | "in_progress" | "done" | "error" | "rejected";
  agent_role: string;
  output: string | null;
  created_at: string;
  updated_at: string;
}

export interface Agent {
  name: string;
  description: string;
  harness: boolean;
}

export interface Feedback {
  id: number;
  card_id: number;
  type: "approve" | "reject" | "comment" | "rerun" | "agent_reply" | "output_snapshot";
  content: string;
  author: string;
  parent_id: number | null;
  created_at: string;
}

export interface HealthStatus {
  claude_cli: boolean;
  claude_authed: boolean;
  version: string | null;
}

export interface TrendingRepo {
  owner: string;
  repo: string;
  full_name: string;
  description: string;
  stars: number;
  stars_period: number;
  language: string;
  url: string;
  topics: string[];
}

export interface SessionInfo {
  project: string;
  dates: string[];
}

export interface ProjectInfo {
  path: string;
  name: string;
  has_claude_md: boolean;
  has_git: boolean;
}
