"use client";

import { useEffect, useRef, useState } from "react";

export interface ModelOption {
  id: string;
  label: string;
}

interface ModelPickerProps {
  models: ModelOption[];
  value: string;
  onChange: (id: string) => void;
}

export function ModelPicker({ models, value, onChange }: ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const currentLabel = models.find((m) => m.id === value)?.label ?? "Model";

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Model: ${currentLabel}`}
        title={currentLabel}
        className="
          rounded-xl h-10 flex items-center justify-center gap-1.5 text-sm
          px-2.5 sm:px-3
          bg-[var(--panel)] text-[var(--text)]
          shadow-[0_1px_2px_rgba(28,25,23,0.06)]
          hover:bg-[#e4ddce] hover:shadow-[0_3px_10px_-2px_rgba(28,25,23,0.15)] hover:-translate-y-px
          active:translate-y-0
          transition-all duration-150
        "
      >
        {/* Sparkle icon shown always — carries the meaning on mobile
            where the model label is hidden to save room. */}
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="M12 3l1.6 4.6L18 9.2l-4.4 1.6L12 15.4l-1.6-4.6L6 9.2l4.4-1.6L12 3z" />
        </svg>
        <span className="hidden sm:inline font-medium">{currentLabel}</span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && (
        <div
          role="listbox"
          // Anchor to the button's right edge so the popup grows
          // leftward — otherwise on narrow viewports (mobile) the
          // 200px popup pushed past the right edge and made the
          // whole page horizontally scrollable.
          className="absolute bottom-full right-0 mb-2 min-w-[200px] max-w-[calc(100vw-2rem)] bg-white border border-[var(--border)] rounded-xl shadow-[0_10px_30px_-6px_rgba(28,25,23,0.18)] overflow-hidden py-1"
        >
          {models.map((m) => (
            <button
              key={m.id}
              type="button"
              role="option"
              aria-selected={value === m.id}
              onClick={() => {
                onChange(m.id);
                setOpen(false);
              }}
              className="w-full text-left px-3 py-2 text-sm text-[var(--text)] hover:bg-[var(--panel)] flex items-center justify-between gap-3"
            >
              <span>{m.label}</span>
              {value === m.id && (
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
