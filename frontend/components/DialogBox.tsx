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

    // Lock background scroll while the dialog is open.
    // Measure any width the scrollbar was taking BEFORE we hide it
    // and add matching padding-right to body so the content doesn't
    // shift horizontally when the scrollbar disappears. scrollbar-gutter
    // on <html> handles most cases already, this is the belt-and-braces
    // path used by mature modal libraries (Radix, React-Aria, MUI).
    const scrollbarWidth =
      window.innerWidth - document.documentElement.clientWidth;
    const body = document.body;
    const prevOverflow = body.style.overflow;
    const prevPaddingRight = body.style.paddingRight;
    body.style.overflow = "hidden";
    if (scrollbarWidth > 0) {
      body.style.paddingRight = `${scrollbarWidth}px`;
    }

    return () => {
      document.removeEventListener("keydown", onKey);
      body.style.overflow = prevOverflow;
      body.style.paddingRight = prevPaddingRight;
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
