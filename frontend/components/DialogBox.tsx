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

    // Bulletproof scroll lock. Setting body.overflow=hidden doesn't
    // work when the scrollbar lives on <html> — the previous
    // paddingRight compensation ended up pushing content inward
    // because the scrollbar was never actually removed.
    //
    // Instead: pin body in place with position:fixed at a negative
    // top offset equal to the current scrollY. Visually nothing
    // moves, the page can no longer scroll, and the html scrollbar
    // is untouched (scrollbar-gutter:stable keeps the gutter
    // reserved). On unmount restore body styles and scroll back to
    // where we were.
    const scrollY = window.scrollY;
    const body = document.body;
    const prev = {
      position: body.style.position,
      top: body.style.top,
      left: body.style.left,
      right: body.style.right,
      width: body.style.width,
    };
    body.style.position = "fixed";
    body.style.top = `-${scrollY}px`;
    body.style.left = "0";
    body.style.right = "0";
    body.style.width = "100%";

    return () => {
      document.removeEventListener("keydown", onKey);
      body.style.position = prev.position;
      body.style.top = prev.top;
      body.style.left = prev.left;
      body.style.right = prev.right;
      body.style.width = prev.width;
      window.scrollTo(0, scrollY);
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
