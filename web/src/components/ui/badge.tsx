import * as React from "react";
import { cn } from "@/lib/utils";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "secondary" | "success" | "destructive" | "warning";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        {
          "bg-indigo-500/20 text-indigo-400": variant === "default",
          "bg-[--color-muted] text-[--color-muted-foreground]": variant === "secondary",
          "bg-emerald-500/20 text-emerald-400": variant === "success",
          "bg-red-500/20 text-red-400": variant === "destructive",
          "bg-amber-500/20 text-amber-400": variant === "warning",
        },
        className
      )}
      {...props}
    />
  );
}
