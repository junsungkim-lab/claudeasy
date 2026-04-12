import * as React from "react";
import { cn } from "@/lib/utils";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "secondary" | "destructive" | "ghost" | "outline";
  size?: "sm" | "md" | "lg" | "icon";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "md", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[--color-ring]",
          {
            "bg-[--color-primary] text-white hover:bg-indigo-500": variant === "default",
            "bg-[--color-secondary] text-[--color-secondary-foreground] hover:bg-zinc-600": variant === "secondary",
            "bg-[--color-destructive] text-white hover:bg-red-500": variant === "destructive",
            "hover:bg-[--color-accent] hover:text-[--color-accent-foreground]": variant === "ghost",
            "border border-[--color-border] hover:bg-[--color-accent]": variant === "outline",
          },
          {
            "h-7 px-2.5 text-xs": size === "sm",
            "h-9 px-4 text-sm": size === "md",
            "h-10 px-6 text-sm": size === "lg",
            "h-8 w-8 p-0": size === "icon",
          },
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
