"use client";

import {
  Activity,
  Zap,
  Database,
  Cpu,
  Timer,
} from "lucide-react";
import { MetricCard } from "@/components/app/MetricCard";
import { BudgetBadge } from "@/components/app/BudgetBadge";
import {
  DEMO_METRICS,
  DEMO_BUDGET_DISTRIBUTION,
  DEMO_COST_OVER_TIME,
} from "@/demo/demoMetrics";
import { DEMO_AUDIT_RECORDS } from "@/demo/demoAudit";
import type { BudgetClass } from "@/demo/types";
import {
  LineChart,
  Line,
  ResponsiveContainer,
} from "recharts";

const BUDGET_META: Record<BudgetClass, { color: string; tailwind: string; model: string; tokens: string }> = {
  low: { color: "#047857", tailwind: "bg-emerald-600", model: "Qwen2.5-3B", tokens: "0" },
  medium: { color: "#3730A3", tailwind: "bg-indigo-700", model: "DeepSeek-R1-7B", tokens: "512" },
  high: { color: "#B45309", tailwind: "bg-amber-600", model: "DeepSeek-R1-7B", tokens: "1024" },
  critical: { color: "#BE123C", tailwind: "bg-rose-700", model: "DeepSeek-R1-7B", tokens: "2048" },
};

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function eventDescription(rec: (typeof DEMO_AUDIT_RECORDS)[number]) {
  if (rec.stopReason === "cache_hit") return "Served from semantic cache";
  if (rec.escalationCount > 0 && rec.verificationResult === "incorrect") return `Escalated to ${rec.budgetClass}, verification failed`;
  if (rec.escalationCount > 0) return `Escalated to ${rec.budgetClass}, verification passed`;
  if (rec.stopReason === "budget_exhausted") return `Budget exhausted at ${rec.reasoningTokensUsed} tokens`;
  if (rec.budgetClass === "low") return `Routed to cheap model, ${rec.outputTokens} output tokens`;
  return `Completed naturally, ${rec.reasoningTokensUsed}/${rec.reasoningTokensAllocated} tokens`;
}

// Baseline cost from demo data average
const baselineCost = DEMO_COST_OVER_TIME.reduce((s, d) => s + d.baseline, 0) / DEMO_COST_OVER_TIME.length;
const deltaPct = Math.round(((DEMO_METRICS.costPerCorrectAnswer - baselineCost) / baselineCost) * 100);

export default function OverviewPage() {
  const m = DEMO_METRICS;
  const savingsPct = Math.round((m.reasoningTokensSaved / m.totalReasoningTokens) * 100);

  return (
    <div className="space-y-8">
      {/* Demo banner */}
      <div className="flex items-center gap-2 rounded-md border border-amber-200/80 bg-amber-50/60 px-3 py-1.5 text-[11px] text-amber-700">
        <Zap className="h-3 w-3 shrink-0" />
        Simulated telemetry — estimated values for demonstration purposes
      </div>

      {/* Hero Metric: Cost per Correct Answer */}
      <div className="flex flex-col items-center py-6">
        <span className="section-label text-[11px] tracking-widest text-muted-foreground/70">
          PRIMARY METRIC
        </span>
        <div className="mt-3 flex items-baseline gap-3">
          <span className="metric-value text-[52px] font-semibold tracking-tight text-foreground leading-none">
            ${m.costPerCorrectAnswer.toFixed(4)}
          </span>
          <span className="font-mono-tight text-sm text-[var(--color-emerald)] font-medium">
            {deltaPct}% vs baseline
          </span>
        </div>
        <span className="mt-1.5 text-[11px] text-muted-foreground/60">
          Cost per correct answer — inference + guardrails + verification + overhead
        </span>
      </div>

      {/* Secondary Metrics Row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Total Requests"
          value={m.totalRequests.toLocaleString()}
          sub="estimated"
          icon={<Activity className="h-4 w-4" />}
        />
        <MetricCard
          label="Tokens Saved"
          value={`${(m.reasoningTokensSaved / 1_000_000).toFixed(1)}M`}
          sub={`${savingsPct}% of total reasoning`}
          trend="up"
          icon={<Cpu className="h-4 w-4" />}
        />
        <MetricCard
          label="Cache Hit Rate"
          value={`${(m.cacheHitRate * 100).toFixed(1)}%`}
          sub="FAISS in-process"
          icon={<Database className="h-4 w-4" />}
        />
        <MetricCard
          label="P95 Latency"
          value={`${(m.p95LatencyMs / 1000).toFixed(1)}s`}
          sub={`${m.p95LatencyMs}ms`}
          icon={<Timer className="h-4 w-4" />}
        />
      </div>

      {/* Routing Distribution + System Signal */}
      <div className="grid gap-6 lg:grid-cols-3 min-w-0">
        {/* Routing Distribution — 2/3 */}
        <div className="lg:col-span-2 min-w-0 rounded-lg border border-border bg-[var(--surface-paper)] p-5">
          <h3 className="section-label text-[11px] tracking-widest text-muted-foreground/70 mb-5">
            ROUTING DISTRIBUTION
          </h3>

          {/* Segmented bar */}
          <div className="flex h-7 w-full overflow-hidden rounded-md">
            {(Object.entries(DEMO_BUDGET_DISTRIBUTION) as [BudgetClass, number][]).map(
              ([cls, pct]) => (
                <div
                  key={cls}
                  className="transition-all"
                  style={{ width: `${pct * 100}%`, backgroundColor: BUDGET_META[cls].color }}
                />
              )
            )}
          </div>

          {/* Labels below */}
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
            {(Object.entries(DEMO_BUDGET_DISTRIBUTION) as [BudgetClass, number][]).map(
              ([cls, pct]) => {
                const meta = BUDGET_META[cls];
                return (
                  <div key={cls} className="space-y-1">
                    <div className="flex items-center gap-1.5">
                      <div className="h-2 w-2 rounded-sm" style={{ backgroundColor: meta.color }} />
                      <span className="text-[11px] font-medium capitalize text-foreground">{cls}</span>
                      <span className="font-mono-tight text-[11px] text-muted-foreground">{(pct * 100).toFixed(0)}%</span>
                    </div>
                    <div className="pl-3.5 text-[10px] text-muted-foreground/60 leading-relaxed">
                      <div>{meta.model}</div>
                      <div className="font-mono-tight">{meta.tokens} max reasoning</div>
                    </div>
                  </div>
                );
              }
            )}
          </div>
        </div>

        {/* System Signal — 1/3 */}
        <div className="space-y-4">
          {/* Circuit Breakers */}
          <div className="rounded-lg border border-border bg-[var(--surface-paper)] p-4 space-y-3">
            <h3 className="section-label text-[11px] tracking-widest text-muted-foreground/70">
              CIRCUIT BREAKERS
            </h3>
            {[
              { label: "GPU Pressure", state: m.gpuCbState },
              { label: "Latency", state: m.latencyCbState },
            ].map((cb) => (
              <div key={cb.label} className="flex items-center gap-2.5">
                <div
                  className={`h-2 w-2 rounded-full ${
                    cb.state === "closed" ? "bg-[var(--color-emerald)]" : "bg-[var(--color-rose)]"
                  }`}
                />
                <span className="text-xs text-foreground">{cb.label}</span>
                <span className="font-mono-tight text-[11px] text-muted-foreground ml-auto capitalize">
                  {cb.state}
                </span>
              </div>
            ))}
          </div>

          {/* Cost sparkline */}
          <div className="rounded-lg border border-border bg-[var(--surface-paper)] p-4">
            <div className="flex items-center justify-between mb-1">
              <h3 className="section-label text-[11px] tracking-widest text-muted-foreground/70">
                COST TREND
              </h3>
              <span className="font-mono-tight text-[10px] text-muted-foreground/50">24h</span>
            </div>
            <div style={{ height: 72 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={DEMO_COST_OVER_TIME}>
                  <Line
                    type="monotone"
                    dataKey="baseline"
                    stroke="var(--border)"
                    strokeWidth={1}
                    strokeDasharray="3 3"
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="cost"
                    stroke="#3730A3"
                    strokeWidth={1.5}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-1 flex items-center gap-4 text-[10px] text-muted-foreground/60">
              <span className="flex items-center gap-1">
                <span className="inline-block h-0.5 w-3 rounded bg-[#3730A3]" /> InferaCordon
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-0.5 w-3 rounded border-t border-dashed border-muted-foreground/40" /> Baseline
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Activity Timeline */}
      <div className="rounded-lg border border-border bg-[var(--surface-paper)] p-5">
        <h3 className="section-label text-[11px] tracking-widest text-muted-foreground/70 mb-4">
          RECENT ACTIVITY
        </h3>
        <div className="space-y-0">
          {DEMO_AUDIT_RECORDS.slice(0, 7).map((rec, i) => (
            <div key={rec.requestId} className="flex gap-4 group">
              {/* Timeline spine */}
              <div className="flex flex-col items-center pt-1">
                <div className={`h-2 w-2 rounded-full shrink-0 ${
                  rec.escalationCount > 0 ? "bg-[var(--color-amber)]"
                  : rec.verificationResult === "incorrect" ? "bg-[var(--color-rose)]"
                  : rec.stopReason === "cache_hit" ? "bg-[var(--color-emerald)]"
                  : "bg-muted-foreground/30"
                }`} />
                {i < 6 && <div className="w-px flex-1 bg-border/60 mt-1" />}
              </div>

              {/* Content */}
              <div className="pb-4 flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono-tight text-[10px] text-muted-foreground/50">{formatTime(rec.timestamp)}</span>
                  <BudgetBadge budgetClass={rec.budgetClass} />
                  {rec.escalationCount > 0 && (
                    <span className="text-[10px] font-medium text-[var(--color-amber)]">escalated</span>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-foreground/80">{eventDescription(rec)}</p>
                <div className="mt-1 flex items-center gap-3 text-[10px] text-muted-foreground/50 font-mono-tight">
                  <span>{rec.requestId.slice(0, 12)}</span>
                  {rec.estimatedCostUsd > 0 && <span>${rec.estimatedCostUsd.toFixed(4)}</span>}
                  <span>{rec.latencyMs}ms</span>
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="pt-2 border-t border-border/40">
          <p className="text-[10px] text-muted-foreground/40">Simulated audit records</p>
        </div>
      </div>
    </div>
  );
}
