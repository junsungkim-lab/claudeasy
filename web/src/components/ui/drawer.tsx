import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export function Drawer({ open, onClose, title, children, className }: DrawerProps) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/40"
          onClick={onClose}
        />
      )}
      <div
        className={cn(
          "fixed top-0 right-0 z-50 h-full w-[480px] max-w-full bg-[--color-card] border-l border-[--color-border] shadow-2xl transition-transform duration-200",
          open ? "translate-x-0" : "translate-x-full",
          className
        )}
      >
        <div className="flex items-center justify-between p-4 border-b border-[--color-border]">
          <h2 className="text-sm font-semibold text-[--color-foreground] truncate">{title}</h2>
          <button
            onClick={onClose}
            className="ml-2 shrink-0 text-[--color-muted-foreground] hover:text-[--color-foreground] transition-colors"
          >
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto h-[calc(100%-57px)]">
          {children}
        </div>
      </div>
    </>
  );
}
