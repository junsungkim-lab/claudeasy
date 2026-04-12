import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export function Dialog({ open, onClose, title, children, className }: DialogProps) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div
        className={cn(
          "relative z-10 bg-[--color-card] border border-[--color-border] rounded-xl shadow-2xl w-full mx-4",
          className
        )}
      >
        {title && (
          <div className="flex items-center justify-between p-4 border-b border-[--color-border]">
            <h2 className="text-sm font-semibold text-[--color-foreground]">{title}</h2>
            <button
              onClick={onClose}
              className="text-[--color-muted-foreground] hover:text-[--color-foreground] transition-colors"
            >
              <X size={16} />
            </button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
