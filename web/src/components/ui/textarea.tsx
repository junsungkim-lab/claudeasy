import * as React from "react";
import { cn } from "@/lib/utils";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "w-full rounded-md border border-[--color-border] bg-[--color-input] px-3 py-2 text-sm text-[--color-foreground] placeholder:text-[--color-muted-foreground] focus:outline-none focus:ring-2 focus:ring-[--color-ring] disabled:opacity-50 resize-none",
      className
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";
