import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "w-full rounded-md border border-[--color-border] bg-[--color-input] px-3 py-1.5 text-sm text-[--color-foreground] placeholder:text-[--color-muted-foreground] focus:outline-none focus:ring-2 focus:ring-[--color-ring] disabled:opacity-50",
      className
    )}
    {...props}
  />
));
Input.displayName = "Input";
