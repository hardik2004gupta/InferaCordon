"use client";

import { cn } from "@/lib/utils";

export type StageStatus = "pending" | "running" | "completed" | "error" | "warning";

export interface PipelineGroup {
  label: string;
  status: StageStatus;
}

const dotStyle: Record<StageStatus, string> = {
  pending: "bg-border",
  running: "bg-[var(--color-indigo)] pipeline-pulse",
  completed: "bg-[var(--color-emerald)]",
  error: "bg-[var(--color-rose)]",
  warning: "bg-[var(--color-amber)]",
};

const labelStyle: Record<StageStatus, string> = {
  pending: "text-muted-foreground/40",
  running: "text-[var(--color-indigo)]",
  completed: "text-foreground/70",
  error: "text-[var(--color-rose)]",
  warning: "text-[var(--color-amber)]",
};

function lineColor(prev: StageStatus): string {
  if (prev === "completed") return "bg-[var(--color-emerald)]/40";
  if (prev === "error") return "bg-[var(--color-rose)]/40";
  if (prev === "warning") return "bg-[var(--color-amber)]/40";
  return "bg-border/60";
}

export function PipelineStages({ groups }: { groups: PipelineGroup[] }) {
  return (
    <div className="flex items-start justify-between px-1 py-3">
      {groups.map((group, i) => (
        <div key={group.label} className="flex items-center">
          {/* Stage column: dot + label */}
          <div className="flex flex-col items-center gap-1.5">
            <div
              className={cn(
                "h-2 w-2 rounded-full transition-all duration-300",
                dotStyle[group.status],
              )}
            />
            <span
              className={cn(
                "text-[9px] uppercase tracking-[0.08em] leading-none transition-colors duration-200 select-none",
                labelStyle[group.status],
              )}
            >
              {group.label}
            </span>
          </div>
          {/* Connecting line */}
          {i < groups.length - 1 && (
            <div
              className={cn(
                "mx-1 h-px w-5 shrink-0 transition-colors duration-300 sm:w-8 lg:w-10",
                lineColor(group.status),
              )}
              style={{ marginTop: "-8px" }}
            />
          )}
        </div>
      ))}
    </div>
  );
}
