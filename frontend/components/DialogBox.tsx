"use client";

import { useEffect } from "react";

interface DialogBoxProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DialogBox({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
}: DialogBoxProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKey);
    // Prevent background scroll while modal is open
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/25 backdrop-blur-[2px]"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        aria-describedby="dialog-description"
        className="bg-white rounded-xl border border-[var(--border)] shadow-[0_24px_60px_-12px_rgba(28,25,23,0.28)] p-6 max-w-sm w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="dialog-title" className="text-lg font-semibold text-[var(--text)] mb-2">
          {title}
        </h2>
        <p id="dialog-description" className="text-sm text-[var(--muted)] leading-relaxed mb-6">
          {description}
        </p>
        <div className="flex gap-2 justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-xl px-4 py-2 text-sm font-medium bg-[#fce8e4] text-[#a63b3b] hover:bg-[#f8d3cd] transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            autoFocus
            className="rounded-xl px-4 py-2 text-sm font-medium bg-[var(--text)] text-[var(--bg)] hover:opacity-90 transition-opacity"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
