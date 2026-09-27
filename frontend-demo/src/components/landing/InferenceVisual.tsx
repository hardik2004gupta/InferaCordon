"use client";

import { motion } from "framer-motion";

const stages = [
  { label: "REQUEST", value: "POST /v1/infer", color: "var(--color-slate)" },
  { label: "COMPLEXITY", value: "score: 7.8", color: "var(--color-indigo)" },
  { label: "BUDGET", value: "1,024 tokens", color: "var(--color-indigo)" },
  { label: "ROUTE", value: "DeepSeek-R1", color: "var(--color-cyan)" },
  { label: "GUARD", value: "pass", color: "var(--color-emerald)" },
  { label: "INFER", value: "687 tokens", color: "var(--color-violet)" },
  { label: "VERIFY", value: "correct", color: "var(--color-teal)" },
  { label: "RESPOND", value: "$0.0089", color: "var(--color-emerald)" },
];

export function InferenceVisual() {
  return (
    <div className="relative w-full overflow-hidden py-6">
      {/* Horizontal pipeline */}
      <div className="relative flex items-center gap-0">
        {stages.map((stage, i) => (
          <div key={stage.label} className="flex items-center">
            {/* Connecting line + traveling dot */}
            {i > 0 && (
              <div className="relative h-px w-6 shrink-0 bg-border sm:w-8">
                <motion.div
                  className="absolute top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full"
                  style={{ backgroundColor: stages[i - 1].color }}
                  initial={{ left: 0, opacity: 0 }}
                  animate={{ left: "100%", opacity: [0, 1, 1, 0] }}
                  transition={{
                    delay: i * 0.35 + 0.6,
                    duration: 0.5,
                    ease: "easeInOut",
                  }}
                />
              </div>
            )}

            {/* Stage node */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                delay: i * 0.35 + 0.3,
                duration: 0.4,
                ease: "easeOut",
              }}
              className="flex shrink-0 flex-col items-center gap-1.5"
            >
              {/* Dot */}
              <motion.div
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: stage.color }}
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{
                  delay: i * 0.35 + 0.5,
                  duration: 0.25,
                  type: "spring",
                  stiffness: 300,
                }}
              />

              {/* Label */}
              <span className="text-[9px] font-medium uppercase tracking-wider text-muted-foreground">
                {stage.label}
              </span>

              {/* Value */}
              <motion.span
                className="font-mono-tight text-[10px] text-foreground"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.35 + 0.7, duration: 0.3 }}
              >
                {stage.value}
              </motion.span>
            </motion.div>
          </div>
        ))}
      </div>

      {/* Summary line */}
      <motion.div
        className="mt-6 flex items-center justify-center gap-4 border-t border-dashed border-border pt-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 3.5, duration: 0.5 }}
      >
        <span className="font-mono-tight text-[10px] text-emerald-700">
          337 tokens saved
        </span>
        <span className="text-[10px] text-muted-foreground/50">|</span>
        <span className="font-mono-tight text-[10px] text-muted-foreground">
          natural_boundary
        </span>
        <span className="text-[10px] text-muted-foreground/50">|</span>
        <span className="font-mono-tight text-[10px] text-muted-foreground">
          2.8s e2e
        </span>
      </motion.div>
    </div>
  );
}
