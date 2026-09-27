"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TraceSpan } from "@/demo/types";

function StatusDot({ status }: { status: TraceSpan["status"] }) {
  const color =
    status === "error"
      ? "bg-[var(--color-rose)]"
      : status === "warning"
      ? "bg-[var(--color-amber)]"
      : "bg-[var(--color-emerald)]";
  return <div className={cn("h-1.5 w-1.5 shrink-0 rounded-full", color)} />;
}

export function TraceWaterfall({ spans }: { spans: TraceSpan[] }) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const maxMs = Math.max(...spans.map((s) => s.startMs + s.durationMs), 1);

  return (
    <div className="space-y-px">
      {spans.map((span, i) => {
        const left = (span.startMs / maxMs) * 100;
        const width = Math.max((span.durationMs / maxMs) * 100, 1.2);
        const isExpanded = expandedIndex === i;
        const isEscalation = span.name === "Escalation";
        const hasAttrs = span.attributes && Object.keys(span.attributes).length > 0;

        return (
          <div key={i}>
            {/* Escalation divider */}
            {isEscalation && (
              <div className="my-2 flex items-center gap-2">
                <div className="h-px flex-1 border-t border-dashed border-[var(--color-amber)]/40" />
                <span className="text-[9px] font-medium uppercase tracking-[0.08em] text-[var(--color-amber)]">
                  Escalation
                </span>
                <div className="h-px flex-1 border-t border-dashed border-[var(--color-amber)]/40" />
              </div>
            )}

            <motion.div
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04, duration: 0.2 }}
            >
              <button
                type="button"
                onClick={() => hasAttrs && setExpandedIndex(isExpanded ? null : i)}
                aria-expanded={hasAttrs ? isExpanded : undefined}
                className={cn(
                  "group flex w-full items-center gap-1.5 rounded px-1 py-[3px] text-left transition-colors",
                  hasAttrs ? "hover:bg-muted/40 cursor-pointer" : "cursor-default",
                )}
              >
                <StatusDot status={span.status} />
                <span className="w-24 shrink-0 truncate text-[10px] text-muted-foreground">
                  {span.name}
                </span>
                <div className="relative h-[14px] flex-1">
                  <div
                    className="absolute top-[5px] h-[4px] rounded-full transition-all"
                    style={{
                      left: `${left}%`,
                      width: `${width}%`,
                      backgroundColor: span.color,
                      opacity: 0.7,
                    }}
                  />
                </div>
                <span className="w-12 shrink-0 text-right font-mono-tight text-[10px] text-muted-foreground">
                  {span.durationMs}ms
                </span>
                {hasAttrs && (
                  <ChevronRight
                    className={cn(
                      "h-3 w-3 shrink-0 text-muted-foreground/40 transition-transform duration-150",
                      isExpanded && "rotate-90",
                    )}
                  />
                )}
              </button>

              {/* Expanded attributes */}
              <AnimatePresence initial={false}>
                {isExpanded && span.attributes && (
                  <motion.div
                    key="attrs"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.15 }}
                    className="overflow-hidden"
                  >
                    <div className="ml-[calc(6px+6px+96px+6px)] mr-6 mb-1 rounded border border-border bg-[var(--surface-inset)] px-2.5 py-1.5 text-[10px]">
                      {Object.entries(span.attributes).map(([k, v]) => (
                        <div key={k} className="flex justify-between gap-3 py-px">
                          <span className="text-muted-foreground">{k}</span>
                          <span className="font-mono-tight text-right">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          </div>
        );
      })}

      {/* Footer */}
      <div className="mt-2 flex items-center justify-between border-t border-border pt-2">
        <span className="text-[9px] text-muted-foreground">
          {spans.length} spans
        </span>
        <span className="font-mono-tight text-[10px] text-muted-foreground">
          {maxMs}ms total
        </span>
      </div>
    </div>
  );
}
