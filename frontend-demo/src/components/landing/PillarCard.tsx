"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

interface PillarCardProps {
  icon: ReactNode;
  title: string;
  description: string;
  detail: string;
  index: number;
}

/* Each pillar gets a unique inline visual based on index */
function PillarVisual({ index }: { index: number }) {
  if (index === 0) {
    /* Guardrails: boundary filter lines */
    return (
      <div className="mb-4 flex items-center gap-1">
        {["PII", "inject", "safety"].map((label) => (
          <div
            key={label}
            className="flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5"
          >
            <div className="h-1 w-1 rounded-full bg-emerald-500" />
            <span className="font-mono-tight text-[9px] text-emerald-700">
              {label}
            </span>
          </div>
        ))}
      </div>
    );
  }

  if (index === 1) {
    /* Governance: version chain */
    return (
      <div className="mb-4 flex items-center gap-1.5">
        {["v1", "v2", "v3"].map((v, i) => (
          <div key={v} className="flex items-center">
            <div
              className={`rounded border px-1.5 py-0.5 font-mono-tight text-[9px] ${
                i === 2
                  ? "border-indigo-200 bg-indigo-50 text-indigo-700"
                  : "border-border bg-muted text-muted-foreground"
              }`}
            >
              {v}
            </div>
            {i < 2 && (
              <div className="mx-0.5 h-px w-3 bg-border" />
            )}
          </div>
        ))}
        <span className="font-mono-tight text-[9px] text-muted-foreground/60 ml-1">
          immutable
        </span>
      </div>
    );
  }

  if (index === 2) {
    /* Cost Optimization: token allocation bar */
    return (
      <div className="mb-4 space-y-1">
        <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
          <div className="h-full w-[35%] bg-emerald-400 rounded-l-full" />
          <div className="h-full w-[25%] bg-indigo-400" />
          <div className="h-full w-[15%] bg-amber-400 rounded-r-full" />
        </div>
        <div className="flex justify-between font-mono-tight text-[9px] text-muted-foreground">
          <span>cached 35%</span>
          <span>routed</span>
          <span>escalated</span>
        </div>
      </div>
    );
  }

  /* Inference Optimization: reasoning stream with delimiter */
  return (
    <div className="mb-4 flex items-center gap-px">
      {Array.from({ length: 16 }).map((_, i) => (
        <div
          key={i}
          className={`h-3 w-1.5 rounded-sm ${
            i < 11
              ? "bg-indigo-300"
              : i === 11
              ? "bg-rose-400"
              : "bg-muted"
          }`}
        />
      ))}
      <span className="ml-2 font-mono-tight text-[9px] text-rose-500">
        {"</think>"}
      </span>
    </div>
  );
}

export function PillarCard({ icon, title, description, detail, index }: PillarCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ delay: index * 0.1, duration: 0.45, ease: "easeOut" }}
      className="group rounded-lg border border-border bg-card p-6 transition-shadow duration-150 hover:shadow-[var(--shadow-md)]"
    >
      <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors group-hover:border-primary/30 group-hover:text-primary">
        {icon}
      </div>
      <h3 className="mb-1.5 text-sm font-semibold tracking-tight text-foreground">
        {title}
      </h3>
      <p className="mb-4 text-[13px] leading-relaxed text-muted-foreground">
        {description}
      </p>
      <PillarVisual index={index} />
      <p className="font-mono-tight text-[11px] text-muted-foreground/60">
        {detail}
      </p>
    </motion.div>
  );
}
