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
          "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400",
          {
            "bg-indigo-500 text-white hover:bg-indigo-600": variant === "default",
            "bg-gray-100 text-gray-700 hover:bg-gray-200": variant === "secondary",
            "bg-red-500 text-white hover:bg-red-600": variant === "destructive",
            "bg-transparent text-gray-600 hover:bg-gray-100 hover:text-gray-900": variant === "ghost",
            "border border-gray-200 bg-white text-gray-700 hover:bg-gray-50": variant === "outline",
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
