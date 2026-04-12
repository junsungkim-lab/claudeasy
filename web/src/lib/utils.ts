import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" });
}

export function formatDateTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(startIso: string, endIso?: string) {
  const start = new Date(startIso).getTime();
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  const diff = Math.floor((end - start) / 1000);
  if (diff < 60) return `${diff}s`;
  const m = Math.floor(diff / 60);
  const s = diff % 60;
  return `${m}m ${s}s`;
}

export function truncate(text: string, maxLen: number) {
  if (!text) return "";
  return text.length > maxLen ? text.slice(0, maxLen) + "..." : text;
}

export function projectName(path: string | null) {
  if (!path) return "Global";
  return path.split("/").at(-1) ?? path;
}
