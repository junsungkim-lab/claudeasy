import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  className?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, ...props }, ref) => (
    <div className="relative">
      <select
        ref={ref}
        className={cn(
          "appearance-none w-full rounded-md border border-[--color-border] bg-[--color-input] pl-3 pr-8 py-1.5 text-sm text-[--color-foreground] focus:outline-none focus:ring-2 focus:ring-[--color-ring] disabled:opacity-50 cursor-pointer",
          className
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        size={14}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-[--color-muted-foreground] pointer-events-none"
      />
    </div>
  )
);
Select.displayName = "Select";
