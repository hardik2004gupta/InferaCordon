"use client";

import { useState } from "react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  ReferenceLine,
} from "recharts";
import { DEMO_METRICS, DEMO_COST_OVER_TIME } from "@/demo/demoMetrics";
import {
  DEMO_QUALITY_DATA,
  DEMO_PERFORMANCE_DATA,
  DEMO_RELIABILITY_DATA,
  DEMO_GOVERNANCE_DATA,
  DEMO_COST_DATA,
} from "@/demo/observabilityData";

const TABS = ["Cost", "Quality", "Reliability", "Performance", "Governance"] as const;
type Tab = (typeof TABS)[number];

const COLORS = {
  indigo: "#3730A3",
  emerald: "#047857",
  amber: "#B45309",
  rose: "#BE123C",
  slate: "#64748B",
};

const BUDGET_COLORS: Record<string, string> = {
  low: COLORS.emerald,
  medium: COLORS.indigo,
  high: COLORS.amber,
  critical: COLORS.rose,
};

const GRID_STROKE = "#E5E5E0";

const tooltipStyle = {
  contentStyle: {
    backgroundColor: "#FFFFFF",
    border: "1px solid #E5E5E0",
    borderRadius: "8px",
    fontSize: "12px",
    fontFamily: "var(--font-mono)",
    boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
  },
};

/* ------------------------------------------------------------------ */
/*  Shared components                                                  */
/* ------------------------------------------------------------------ */

function SectionCard({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-[var(--color-border)] bg-white p-5 shadow-sm ${className}`}>
      {children}
    </div>
  );
}

function ChartHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <>
      <h3 className="section-label">{title}</h3>
      {sub && <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">{sub}</p>}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Cost Tab                                                           */
/* ------------------------------------------------------------------ */

function CostTab() {
  const baselineAvg = DEMO_COST_OVER_TIME.reduce((s, d) => s + d.baseline, 0) / DEMO_COST_OVER_TIME.length;
  const costAvg = DEMO_COST_OVER_TIME.reduce((s, d) => s + d.cost, 0) / DEMO_COST_OVER_TIME.length;
  const deltaPct = (((baselineAvg - costAvg) / baselineAvg) * 100).toFixed(0);

  const cacheHitPct = DEMO_METRICS.cacheHitRate * 100;
  const cacheData = [
    { name: "Hits", value: cacheHitPct },
    { name: "Misses", value: 100 - cacheHitPct },
  ];

  const savingsData = DEMO_COST_DATA.tokenSavingsByClass
    .filter((d) => d.allocated > 0)
    .map((d) => ({
      budgetClass: d.budgetClass,
      saved: Math.round(d.saved / 1000),
      used: Math.round((d.allocated - d.saved) / 1000),
    }));

  return (
    <div className="space-y-6">
      {/* Hero metric */}
      <SectionCard>
        <div className="flex flex-col sm:flex-row sm:items-end gap-4">
          <div>
            <p className="section-label">Cost per Correct Answer</p>
            <div className="mt-1 flex items-baseline gap-3">
              <span className="text-3xl font-semibold font-mono-tight text-[var(--color-text)]">
                ${DEMO_METRICS.costPerCorrectAnswer.toFixed(4)}
              </span>
              <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-[#047857]">
                -{deltaPct}% vs baseline
              </span>
            </div>
            <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
              Primary optimization metric across {DEMO_METRICS.totalRequests.toLocaleString()} requests
            </p>
          </div>
        </div>
      </SectionCard>

      {/* Cost over time + Cache donut */}
      <div className="grid gap-6 lg:grid-cols-3 min-w-0">
        <SectionCard className="lg:col-span-2 min-w-0">
          <ChartHeader title="Cost per Request Over Time" sub="InferaCordon vs. uncontrolled baseline" />
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={DEMO_COST_OVER_TIME} margin={{ top: 20, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="hour" tick={{ fontSize: 11 }} stroke="#94a3b8" tickLine={false} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" tickLine={false} axisLine={false} tickFormatter={(v: number) => `$${v.toFixed(3)}`} />
              <Tooltip {...tooltipStyle} formatter={((v: number) => [`$${v.toFixed(4)}`, ""]) as never} />
              <Line type="monotone" dataKey="cost" name="InferaCordon" stroke={COLORS.indigo} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="baseline" name="Baseline" stroke={COLORS.slate} strokeWidth={1.5} strokeDasharray="6 3" dot={false} />
            </LineChart>
          </ResponsiveContainer>
          <div className="mt-2 flex gap-5 text-xs text-[var(--color-text-secondary)]">
            <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 rounded" style={{ backgroundColor: COLORS.indigo }} /> InferaCordon</span>
            <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 rounded border-b border-dashed" style={{ borderColor: COLORS.slate }} /> Baseline</span>
          </div>
        </SectionCard>

        <SectionCard>
          <ChartHeader title="Cache Hit Rate" />
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={cacheData} cx="50%" cy="50%" innerRadius={50} outerRadius={72} paddingAngle={3} dataKey="value" startAngle={90} endAngle={-270}>
                <Cell fill={COLORS.indigo} />
                <Cell fill="#E5E5E0" />
              </Pie>
              <Tooltip {...tooltipStyle} formatter={((v: number) => [`${v.toFixed(1)}%`, ""]) as never} />
            </PieChart>
          </ResponsiveContainer>
          <p className="text-center text-2xl font-semibold font-mono-tight text-[var(--color-text)]">
            {cacheHitPct.toFixed(1)}%
          </p>
          <p className="text-center text-xs text-[var(--color-text-secondary)] mt-0.5">
            {DEMO_COST_DATA.cacheContribution.totalSaved.toLocaleString()} requests served from cache
          </p>
        </SectionCard>
      </div>

      {/* Token savings */}
      <SectionCard>
        <ChartHeader title="Token Savings by Budget Class" sub="Thousands of reasoning tokens saved vs. used" />
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={savingsData} margin={{ top: 20, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
            <XAxis dataKey="budgetClass" tick={{ fontSize: 11 }} stroke="#94a3b8" tickLine={false} />
            <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" tickLine={false} axisLine={false} tickFormatter={(v: number) => `${v}k`} />
            <Tooltip {...tooltipStyle} formatter={((v: number) => [`${v}k tokens`, ""]) as never} />
            <Bar dataKey="saved" name="Saved" fill={COLORS.emerald} radius={[4, 4, 0, 0]} stackId="a" />
            <Bar dataKey="used" name="Used" fill="#D4D4CE" radius={[4, 4, 0, 0]} stackId="a" />
          </BarChart>
        </ResponsiveContainer>
        <div className="mt-2 flex gap-5 text-xs text-[var(--color-text-secondary)]">
          <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS.emerald }} /> Saved</span>
          <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: "#D4D4CE" }} /> Used</span>
        </div>
      </SectionCard>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Quality Tab                                                        */
/* ------------------------------------------------------------------ */

function QualityTab() {
  return (
    <div className="space-y-6">
      {/* Verification by type + Quality trend */}
      <div className="grid gap-6 lg:grid-cols-2 min-w-0">
        <SectionCard className="min-w-0">
          <ChartHeader title="Verification Pass/Fail by Task Type" />
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={DEMO_QUALITY_DATA.verificationByType} margin={{ top: 20, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="type" tick={{ fontSize: 11 }} stroke="#94a3b8" tickLine={false} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" tickLine={false} axisLine={false} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="passed" name="Passed" fill={COLORS.emerald} radius={[0, 0, 0, 0]} stackId="a" />
              <Bar dataKey="failed" name="Failed" fill={COLORS.rose} radius={[4, 4, 0, 0]} stackId="a" />
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-2 flex gap-5 text-xs text-[var(--color-text-secondary)]">
            <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS.emerald }} /> Passed</span>
            <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS.rose }} /> Failed</span>
          </div>
        </SectionCard>

        <SectionCard className="min-w-0">
          <ChartHeader title="Quality Trend (LLM Judge)" sub={`Dashed line = quality floor (${DEMO_QUALITY_DATA.qualityFloor})`} />
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={DEMO_QUALITY_DATA.qualityTrend} margin={{ top: 20, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="hour" tick={{ fontSize: 11 }} stroke="#94a3b8" tickLine={false} />
              <YAxis domain={[3.0, 4.5]} tick={{ fontSize: 11 }} stroke="#94a3b8" tickLine={false} axisLine={false} />
              <Tooltip {...tooltipStyle} formatter={((v: number) => [v.toFixed(2), ""]) as never} />
              <ReferenceLine y={DEMO_QUALITY_DATA.qualityFloor} stroke={COLORS.rose} strokeDasharray="6 3" strokeWidth={1.5} />
              <Line type="monotone" dataKey="score" name="Avg Score" stroke={COLORS.indigo} strokeWidth={2} dot={{ r: 2.5, fill: COLORS.indigo }} />
            </LineChart>
          </ResponsiveContainer>
        </SectionCard>
      </div>

      {/* Escalation table */}
      <SectionCard>
        <ChartHeader title="Escalation Rates by Budget Class" />
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)]">
                <th className="text-left py-2.5 px-3 section-label font-medium">From</th>
                <th className="text-left py-2.5 px-3 section-label font-medium">To</th>
                <th className="text-right py-2.5 px-3 section-label font-medium">Count</th>
                <th className="text-right py-2.5 px-3 section-label font-medium">Rate</th>
              </tr>
            </thead>
            <tbody>
              {DEMO_QUALITY_DATA.escalationsByBudget.map((e) => (
                <tr key={e.from} className="border-b border-[var(--color-border)] last:border-0">
                  <td className="py-2.5 px-3">
                    <span className="inline-block rounded-full px-2.5 py-0.5 text-xs font-medium text-white" style={{ backgroundColor: BUDGET_COLORS[e.from] }}>{e.from}</span>
                  </td>
                  <td className="py-2.5 px-3">
                    <span className="inline-block rounded-full px-2.5 py-0.5 text-xs font-medium text-white" style={{ backgroundColor: BUDGET_COLORS[e.to] }}>{e.to}</span>
                  </td>
                  <td className="py-2.5 px-3 text-right font-mono-tight text-[var(--color-text)]">{e.count}</td>
                  <td className="py-2.5 px-3 text-right font-mono-tight text-[var(--color-text)]">
                    {e.count > 0 ? `${((e.count / DEMO_METRICS.totalRequests) * 100).toFixed(2)}%` : "0%"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Reliability Tab                                                    */
/* ------------------------------------------------------------------ */

function StatusIndicator({ label, value, status }: { label: string; value: string; status: "ok" | "warn" | "error" }) {
  const borderColor = status === "ok" ? "#047857" : status === "warn" ? "#B45309" : "#BE123C";
  const dotColor = status === "ok" ? "bg-[#047857]" : status === "warn" ? "bg-[#B45309]" : "bg-[#BE123C]";
  const statusLabel = status === "ok" ? "Healthy" : status === "warn" ? "Degraded" : "Open";

  return (
    <SectionCard>
      <div className="flex items-center justify-between">
        <p className="section-label">{label}</p>
        <div className="flex items-center gap-1.5">
          <div className={`h-2 w-2 rounded-full ${dotColor}`} />
          <span className="text-xs font-medium" style={{ color: borderColor }}>{statusLabel}</span>
        </div>
      </div>
      <p className="mt-3 text-2xl font-semibold font-mono-tight text-[var(--color-text)]">{value}</p>
    </SectionCard>
  );
}

function ReliabilityTab() {
  const eventColor: Record<string, string> = {
    recovery: "bg-[#047857]",
    incident: "bg-[#BE123C]",
    warning: "bg-[#B45309]",
  };

  return (
    <div className="space-y-6">
      {/* Status indicators */}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatusIndicator label="GPU Pressure CB" value="Closed" status="ok" />
        <StatusIndicator label="Latency CB" value="Closed" status="ok" />
        <StatusIndicator label="Admission Control" value={`${DEMO_RELIABILITY_DATA.admissionQueueDepth} / ${DEMO_RELIABILITY_DATA.admissionCeiling}`} status="ok" />
      </div>

      {/* Uptime */}
      <SectionCard>
        <div className="flex items-baseline gap-3">
          <p className="section-label">Uptime (24h)</p>
          <span className="text-3xl font-semibold font-mono-tight text-[var(--color-text)]">{DEMO_RELIABILITY_DATA.uptime}%</span>
          <span className="text-xs text-[var(--color-text-secondary)]">{DEMO_RELIABILITY_DATA.totalFailures} failures recorded</span>
        </div>
      </SectionCard>

      {/* Recent events */}
      <SectionCard>
        <ChartHeader title="Recent Events" />
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)]">
                <th className="text-left py-2.5 px-3 section-label font-medium">Time</th>
                <th className="text-left py-2.5 px-3 section-label font-medium">Event</th>
                <th className="text-left py-2.5 px-3 section-label font-medium">Type</th>
              </tr>
            </thead>
            <tbody>
              {DEMO_RELIABILITY_DATA.recentEvents.map((e, i) => (
                <tr key={i} className="border-b border-[var(--color-border)] last:border-0">
                  <td className="py-2.5 px-3 font-mono-tight text-xs text-[var(--color-text-secondary)]">
                    {new Date(e.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </td>
                  <td className="py-2.5 px-3 text-[var(--color-text)]">{e.event}</td>
                  <td className="py-2.5 px-3">
                    <div className="flex items-center gap-1.5">
                      <div className={`h-2 w-2 rounded-full ${eventColor[e.type] ?? "bg-gray-400"}`} />
                      <span className="text-xs capitalize text-[var(--color-text-secondary)]">{e.type}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Performance Tab                                                    */
/* ------------------------------------------------------------------ */

function SvgGauge({ label, value, unit, color }: { label: string; value: number; unit: string; color: string }) {
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const filled = (value / 100) * circumference;

  return (
    <SectionCard>
      <p className="section-label">{label}</p>
      <div className="mt-4 relative mx-auto h-28 w-28">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle cx="50" cy="50" r={radius} fill="none" stroke="#E5E5E0" strokeWidth="7" />
          <circle
            cx="50" cy="50" r={radius} fill="none" stroke={color} strokeWidth="7"
            strokeDasharray={`${filled} ${circumference}`}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-semibold font-mono-tight text-[var(--color-text)]">{value}%</span>
        </div>
      </div>
      <p className="mt-2 text-center text-xs text-[var(--color-text-secondary)]">{unit}</p>
    </SectionCard>
  );
}

function PerformanceTab() {
  return (
    <div className="space-y-6">
      {/* Gauges + throughput */}
      <div className="grid gap-4 sm:grid-cols-3">
        <SvgGauge label="GPU Utilization" value={DEMO_PERFORMANCE_DATA.gpuUtilization} unit="A100 80GB" color={COLORS.indigo} />
        <SvgGauge label="KV-Cache Utilization" value={DEMO_PERFORMANCE_DATA.kvCacheUtilization} unit="Cache pressure" color={COLORS.amber} />
        <SectionCard>
          <p className="section-label">Decode Throughput</p>
          <p className="mt-4 text-3xl font-semibold font-mono-tight text-[var(--color-text)]">
            {DEMO_PERFORMANCE_DATA.decodeTokensPerSec}
          </p>
          <p className="mt-1 text-xs text-[var(--color-text-secondary)]">tokens/sec</p>
        </SectionCard>
      </div>

      {/* TTFT trend */}
      <SectionCard>
        <ChartHeader title="Time to First Token (TTFT)" sub="P50 / P95 / P99 percentiles over time" />
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={DEMO_PERFORMANCE_DATA.ttftTrend} margin={{ top: 20, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
            <XAxis dataKey="hour" tick={{ fontSize: 11 }} stroke="#94a3b8" tickLine={false} />
            <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" tickLine={false} axisLine={false} tickFormatter={(v: number) => `${v}ms`} />
            <Tooltip {...tooltipStyle} formatter={((v: number) => [`${v}ms`, ""]) as never} />
            <Line type="monotone" dataKey="ttft" name="TTFT" stroke={COLORS.indigo} strokeWidth={2} dot={{ r: 2.5, fill: COLORS.indigo }} />
          </LineChart>
        </ResponsiveContainer>
      </SectionCard>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Governance Tab                                                     */
/* ------------------------------------------------------------------ */

function GovernanceTab() {
  return (
    <div className="space-y-6">
      {/* Policy distribution */}
      <SectionCard>
        <ChartHeader title="Active Policies" />
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)]">
                <th className="text-left py-2.5 px-3 section-label font-medium">Tenant</th>
                <th className="text-left py-2.5 px-3 section-label font-medium">Policy ID</th>
                <th className="text-right py-2.5 px-3 section-label font-medium">Requests</th>
              </tr>
            </thead>
            <tbody>
              {DEMO_GOVERNANCE_DATA.policyDistribution.map((p) => (
                <tr key={p.tenant} className="border-b border-[var(--color-border)] last:border-0">
                  <td className="py-2.5 px-3 text-[var(--color-text)]">{p.tenant}</td>
                  <td className="py-2.5 px-3 font-mono-tight text-xs text-[var(--color-text)]">{p.policy}</td>
                  <td className="py-2.5 px-3 text-right font-mono-tight text-[var(--color-text)]">{p.requests.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <div className="grid gap-6 lg:grid-cols-2 min-w-0">
        {/* Guardrail events bar chart */}
        <SectionCard className="min-w-0">
          <ChartHeader title="Guardrail Events by Type" />
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={DEMO_GOVERNANCE_DATA.guardrailEvents} margin={{ top: 20, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="type" tick={{ fontSize: 11 }} stroke="#94a3b8" tickLine={false} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" tickLine={false} axisLine={false} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" name="Count" radius={[4, 4, 0, 0]}>
                {DEMO_GOVERNANCE_DATA.guardrailEvents.map((entry, i) => {
                  const color = entry.type === "Block" ? COLORS.rose : entry.type === "Flag" ? COLORS.amber : COLORS.emerald;
                  return <Cell key={i} fill={color} />;
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>

        {/* Tenant activity */}
        <SectionCard>
          <ChartHeader title="Tenant Activity" />
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)]">
                  <th className="text-left py-2.5 px-3 section-label font-medium">Tenant</th>
                  <th className="text-right py-2.5 px-3 section-label font-medium">Requests</th>
                  <th className="text-right py-2.5 px-3 section-label font-medium">Cost</th>
                  <th className="text-right py-2.5 px-3 section-label font-medium">Avg Latency</th>
                </tr>
              </thead>
              <tbody>
                {DEMO_GOVERNANCE_DATA.tenantActivity.map((t) => (
                  <tr key={t.tenant} className="border-b border-[var(--color-border)] last:border-0">
                    <td className="py-2.5 px-3 text-[var(--color-text)]">{t.tenant}</td>
                    <td className="py-2.5 px-3 text-right font-mono-tight text-[var(--color-text)]">{t.requests.toLocaleString()}</td>
                    <td className="py-2.5 px-3 text-right font-mono-tight text-[var(--color-text)]">${t.cost.toFixed(2)}</td>
                    <td className="py-2.5 px-3 text-right font-mono-tight text-[var(--color-text)]">{t.avgLatency}ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function ObservabilityPage() {
  const [activeTab, setActiveTab] = useState<Tab>("Cost");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-[var(--color-text)]">Observability</h2>
        <p className="text-sm text-[var(--color-text-secondary)] mt-0.5">
          {DEMO_METRICS.totalRequests.toLocaleString()} requests tracked across all tenants
        </p>
      </div>

      {/* Tab bar */}
      <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-[var(--color-border)]">
        {TABS.map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2.5 text-sm whitespace-nowrap transition-colors relative ${
              activeTab === tab
                ? "font-medium text-[var(--color-text)]"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)]"
            }`}
          >
            {tab}
            {activeTab === tab && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#3730A3] rounded-full" />
            )}
          </button>
        ))}
      </div>

      <div role="tabpanel" aria-label={`${activeTab} tab content`}>
      {activeTab === "Cost" && <CostTab />}
      {activeTab === "Quality" && <QualityTab />}
      {activeTab === "Reliability" && <ReliabilityTab />}
      {activeTab === "Performance" && <PerformanceTab />}
      {activeTab === "Governance" && <GovernanceTab />}
      </div>
    </div>
  );
}
