import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value: string;
  sub?: string;
  icon?: ReactNode;
  trend?: "up" | "down" | "neutral";
  className?: string;
  prominent?: boolean;
}

export function MetricCard({ label, value, sub, icon, trend, className, prominent }: MetricCardProps) {
  return (
    <div className={cn(
      "rounded-lg border border-border bg-[var(--surface-paper)] p-4 transition-shadow hover:shadow-[var(--shadow-sm)]",
      prominent && "border-primary/10 bg-primary/[0.02]",
      className
    )}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium text-muted-foreground">{label}</span>
        {icon && <span className="text-muted-foreground/40">{icon}</span>}
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="metric-value text-[22px] font-semibold tracking-tight text-foreground">
          {value}
        </span>
        {sub && (
          <span
            className={cn(
              "font-mono-tight text-[10px]",
              trend === "up" && "text-[var(--color-emerald)]",
              trend === "down" && "text-[var(--color-emerald)]",
              (!trend || trend === "neutral") && "text-muted-foreground/60"
            )}
          >
            {sub}
          </span>
        )}
      </div>
    </div>
  );
}
