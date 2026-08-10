/**
 * Dashboard — five-tab observability surface per CLAUDE.md §22.3.
 * Cost | Quality | Reliability | Performance | Governance
 * All data from Prometheus API — zero hardcoded values.
 * Uses Recharts per §25.
 */
import { useState, useEffect, useCallback } from "react";
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { Q, queryRange, queryInstant } from "../lib/prometheus.js";

const TABS = ["Cost", "Quality", "Reliability", "Performance", "Governance"];

const tooltipStyle = {
  backgroundColor: "#1A2332",
  border: "1px solid rgba(255,255,255,0.08)",
  color: "#F0F6FC",
  fontSize: 11,
  fontFamily: "var(--font-mono)",
  borderRadius: 6,
};

// ─── data hooks ─────────────────────────────────────────────────────────────

function useRange(promql, { step = 60, windowMin = 60 } = {}) {
  const [data, setData] = useState([]);
  const [error, setError] = useState(null);
  const load = useCallback(async () => {
    if (!promql) return;
    try {
      const now = Math.floor(Date.now() / 1000);
      const rows = await queryRange(promql, now - windowMin * 60, now, step);
      setData(rows.map(([ts, v]) => ({
        t: new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        v: parseFloat(v),
      })));
      setError(null);
    } catch (e) { setError(e.message); }
  }, [promql, step, windowMin]);

  useEffect(() => { load(); const id = setInterval(load, 30_000); return () => clearInterval(id); }, [load]);
  return { data, error };
}

function useInstant(queries) {
  const [values, setValues] = useState({});
  const load = useCallback(async () => {
    const results = await Promise.allSettled(
      Object.entries(queries).map(async ([k, q]) => [k, await queryInstant(q)])
    );
    const next = {};
    results.forEach((r) => { if (r.status === "fulfilled") { const [k, v] = r.value; next[k] = v; } });
    setValues(next);
  }, []);
  useEffect(() => { load(); const id = setInterval(load, 15_000); return () => clearInterval(id); }, [load]);
  return values;
}

// ─── atoms ───────────────────────────────────────────────────────────────────

function Unavail() {
  return <div style={{ padding: "var(--space-6)", textAlign: "center", color: "var(--text-gov-3)", fontSize: 12 }}>PROMETHEUS UNAVAILABLE</div>;
}

function MetricCard({ label, value, unit = "" }) {
  return (
    <div style={{ background: "rgba(255,255,255,0.04)", borderRadius: "var(--radius)", padding: "var(--space-4) var(--space-5)", border: "1px solid var(--border-gov)", flex: "1 1 150px" }}>
      <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-gov-3)", letterSpacing: "0.07em", marginBottom: 8, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 20, fontWeight: 700, color: "var(--text-gov)" }}>
        {value != null ? `${value}${unit}` : "—"}
      </div>
    </div>
  );
}

function STitle({ children }) {
  return <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-gov-2)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "var(--space-3)", marginTop: "var(--space-5)" }}>{children}</div>;
}

function MiniChart({ data, error, color = "#4F46E5", fmt, refY, refLabel, height = 180, unit = "" }) {
  if (error) return <Unavail />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis dataKey="t" tick={{ fontSize: 9, fill: "#64748B", fontFamily: "var(--font-mono)" }} />
        <YAxis tick={{ fontSize: 9, fill: "#64748B", fontFamily: "var(--font-mono)" }} tickFormatter={fmt} />
        <Tooltip contentStyle={tooltipStyle} formatter={fmt ? (v) => [fmt(v), unit] : undefined} />
        {refY != null && <ReferenceLine y={refY} stroke="#F59E0B" strokeDasharray="6 3" label={{ value: refLabel, fill: "#F59E0B", fontSize: 9 }} />}
        <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ─── Cost ────────────────────────────────────────────────────────────────────

function CostTab() {
  const { data: costLine, error: e1 } = useRange(Q.costPerHour);
  const { data: cacheLine, error: e2 } = useRange(Q.cacheHitRate);
  const v = useInstant({ cost: Q.costPerHour, hit: Q.cacheHitRate, rps: Q.rps });
  return (
    <div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <MetricCard label="Cost / Hour (USD)" value={v.cost != null ? v.cost.toFixed(4) : null} />
        <MetricCard label="Cache Hit Rate" value={v.hit != null ? `${(v.hit * 100).toFixed(1)}` : null} unit="%" />
        <MetricCard label="Requests / sec" value={v.rps != null ? v.rps.toFixed(2) : null} />
      </div>
      <STitle>Cost / Hour — 60 min</STitle>
      <MiniChart data={costLine} error={e1} color="#4F46E5" unit="USD/hr" />
      <STitle>Cache Hit Rate — 60 min</STitle>
      <MiniChart data={cacheLine} error={e2} color="#10B981" fmt={(v) => `${(v * 100).toFixed(0)}%`} height={140} unit="%" />
    </div>
  );
}

// ─── Quality ─────────────────────────────────────────────────────────────────

function QualityTab() {
  const { data: qualLine, error } = useRange(Q.avgQuality);
  const v = useInstant({ quality: Q.avgQuality, escalRate: Q.escalRate });
  return (
    <div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <MetricCard label="Avg Judge Score (1–5)" value={v.quality?.toFixed(2)} />
        <MetricCard label="Escalation Rate" value={v.escalRate != null ? `${(v.escalRate * 100).toFixed(1)}` : null} unit="%" />
      </div>
      <STitle>Rolling Quality Score — 60 min</STitle>
      <MiniChart data={qualLine} error={error} color="#4F46E5" refY={3.5} refLabel="Quality floor" height={200} />
    </div>
  );
}

// ─── Reliability ──────────────────────────────────────────────────────────────

function ReliabilityTab() {
  const { data: latLine, error } = useRange(Q.p95Latency);
  const v = useInstant({ gpuCb: Q.gpuCbOpen, latCb: Q.latCbOpen, p95: Q.p95Latency });

  function CB({ label, val }) {
    const open = val === 1;
    return (
      <div style={{ background: "rgba(255,255,255,0.03)", border: `1px solid ${open ? "#EF4444" : "#10B981"}`, borderRadius: "var(--radius)", padding: "var(--space-4) var(--space-5)", flex: "1 1 200px", display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 10, height: 10, borderRadius: "50%", background: val == null ? "#F59E0B" : open ? "#EF4444" : "#10B981", animation: open ? "cbPulse 1.5s ease infinite" : "none" }} />
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-gov)" }}>{label}</div>
          <div style={{ fontSize: 10, color: open ? "#EF4444" : "#10B981", fontWeight: 600, marginTop: 2 }}>
            {val == null ? "…" : open ? "OPEN — DEGRADED" : "CLOSED — HEALTHY"}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: "var(--space-4)" }}>
        <CB label="GPU Pressure CB" val={v.gpuCb} />
        <CB label="Latency CB" val={v.latCb} />
        <MetricCard label="P95 Latency (ms)" value={v.p95?.toFixed(0)} />
      </div>
      <STitle>P95 Latency — 60 min</STitle>
      <MiniChart data={latLine} error={error} color="#4F46E5" refY={4000} refLabel="SLO 4000ms" height={200} />
      <style>{`@keyframes cbPulse { 0%,100%{opacity:1} 50%{opacity:0.3} }`}</style>
    </div>
  );
}

// ─── Performance ──────────────────────────────────────────────────────────────

function PerformanceTab() {
  const { data: rpsLine, error: e1 } = useRange(Q.rps, { step: 30, windowMin: 30 });
  const v = useInstant({ rps: Q.rps, p95: Q.p95Latency, guardBlock: Q.guardBlock });
  return (
    <div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <MetricCard label="Requests / sec" value={v.rps?.toFixed(2)} />
        <MetricCard label="P95 Latency (ms)" value={v.p95?.toFixed(0)} />
        <MetricCard label="Guardrail Block Rate" value={v.guardBlock != null ? `${(v.guardBlock * 100).toFixed(2)}` : null} unit="%" />
      </div>
      <STitle>Request Rate — 30 min</STitle>
      <MiniChart data={rpsLine} error={e1} color="#4F46E5" height={180} />
    </div>
  );
}

// ─── Governance ──────────────────────────────────────────────────────────────

function GovernanceTab() {
  const { data: guardLine } = useRange(Q.guardBlock);
  const v = useInstant({
    guardBlock: Q.guardBlock,
    fastPath: Q.fastPath,
    escalRate: Q.escalRate,
    rateLim: "increase(ic_rate_limit_hits_total[5m])",
  });

  const stats = [
    { label: "Guardrail Block Rate", value: v.guardBlock != null ? `${(v.guardBlock * 100).toFixed(2)}%` : "—" },
    { label: "Fast-Path Rate", value: v.fastPath != null ? `${(v.fastPath * 100).toFixed(1)}%` : "—" },
    { label: "Escalation Rate", value: v.escalRate != null ? `${(v.escalRate * 100).toFixed(1)}%` : "—" },
    { label: "Rate Limit Hits (5m)", value: v.rateLim?.toFixed(0) ?? "—" },
  ];

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10 }}>
        {stats.map((s) => (
          <div key={s.label} style={{ background: "rgba(255,255,255,0.04)", border: "1px solid var(--border-gov)", borderRadius: "var(--radius)", padding: "var(--space-4)" }}>
            <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-gov-3)", letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 6 }}>{s.label}</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 700, color: "var(--text-gov)" }}>{s.value}</div>
          </div>
        ))}
      </div>
      <STitle>Guardrail Block Rate — 60 min</STitle>
      <MiniChart data={guardLine} error={null} color="#EF4444" fmt={(v) => `${(v * 100).toFixed(2)}%`} height={180} />
    </div>
  );
}

// ─── Root ────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [tab, setTab] = useState("Cost");
  const content = { Cost: <CostTab />, Quality: <QualityTab />, Reliability: <ReliabilityTab />, Performance: <PerformanceTab />, Governance: <GovernanceTab /> };

  return (
    <div style={{ padding: "var(--space-8)", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <div style={{ marginBottom: "var(--space-6)" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>Observability Dashboard</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>Live Prometheus metrics. Auto-refreshes every 30 s.</p>
      </div>

      <div style={{ display: "flex", gap: 2, background: "var(--bg-gov)", borderRadius: "var(--radius-lg)", padding: 4, marginBottom: "var(--space-6)", border: "1px solid var(--border-gov)", width: "fit-content" }}>
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            style={{ padding: "var(--space-2) var(--space-5)", borderRadius: "var(--radius)", border: "none", background: tab === t ? "var(--accent)" : "transparent", color: tab === t ? "#fff" : "var(--text-gov-2)", fontSize: 12, fontWeight: tab === t ? 600 : 400, cursor: "pointer", transition: "background var(--transition), color var(--transition)", letterSpacing: "0.02em" }}
          >{t}</button>
        ))}
      </div>

      <div style={{ background: "var(--bg-gov)", borderRadius: "var(--radius-lg)", padding: "var(--space-6)", border: "1px solid var(--border-gov)", boxShadow: "var(--shadow-gov)" }}>
        {content[tab]}
      </div>
    </div>
  );
}
