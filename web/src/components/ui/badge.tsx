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
          "bg-indigo-100 text-indigo-700": variant === "default",
          "bg-gray-100 text-gray-600": variant === "secondary",
          "bg-emerald-100 text-emerald-700": variant === "success",
          "bg-red-100 text-red-700": variant === "destructive",
          "bg-amber-100 text-amber-700": variant === "warning",
        },
        className
      )}
      {...props}
    />
  );
}
