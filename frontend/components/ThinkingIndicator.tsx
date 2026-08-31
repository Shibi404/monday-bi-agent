"use client";

import { useEffect, useState } from "react";

const PHRASES = [
  "Thinking",
  "Brainstorming",
  "Reasoning through the data",
  "Cross-checking columns",
  "Running the numbers",
  "Drafting your answer",
];

export function ThinkingIndicator() {
  const [i, setI] = useState(0);

  useEffect(() => {
    const id = setInterval(
      () => setI((x) => (x + 1) % PHRASES.length),
      2200,
    );
    return () => clearInterval(id);
  }, []);

  return (
    <div className="mt-1">
      {/* key={i} remounts the span so the fade-in runs on every phrase */}
      <div
        key={i}
        className="text-sm text-[var(--muted)] italic animate-[thinkingPulse_2.2s_ease-in-out_infinite]"
      >
        {PHRASES[i]}…
      </div>
      <div className="text-xs text-[var(--muted)]/70 mt-1.5">
        Using the free Gemini tier — replies can take a few seconds.
      </div>
      <style>{`
        @keyframes thinkingPulse {
          0%   { opacity: 0; transform: translateY(2px); }
          15%  { opacity: 1; transform: translateY(0); }
          85%  { opacity: 1; transform: translateY(0); }
          100% { opacity: 0.4; transform: translateY(-1px); }
        }
      `}</style>
    </div>
  );
}
