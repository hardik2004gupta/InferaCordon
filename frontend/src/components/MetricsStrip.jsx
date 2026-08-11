/**
 * MetricsStrip — compact top-of-page live KPI bar.
 * Polls Prometheus every 10 seconds for ic_ metrics.
 * Shows explicit UNAVAILABLE when Prometheus is unreachable.
 */
import { useState, useEffect } from "react";
import { scalarInstant, Q } from "../lib/prometheus.js";

function MetricCell({ label, value, unit = "", mono = true }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 90 }}>
      <span style={{ fontSize: 10, color: "var(--text-gov-2)", letterSpacing: "0.06em", fontWeight: 600, textTransform: "uppercase" }}>
        {label}
      </span>
      <span
        style={{
          fontFamily: mono ? "var(--font-mono)" : "var(--font-ui)",
          fontSize: 15,
          fontWeight: 500,
          color: value == null ? "var(--text-gov-3)" : "var(--text-gov)",
        }}
      >
        {value == null ? "—" : `${value}${unit}`}
      </span>
    </div>
  );
}

export default function MetricsStrip() {
  const [metrics, setMetrics] = useState({});
  const [loading, setLoading] = useState(true);

  async function refresh() {
    try {
      const [rps, p95, hit, cost, quality] = await Promise.all([
        scalarInstant(Q.rps),
        scalarInstant(Q.p95Latency),
        scalarInstant(Q.cacheHitRate),
        scalarInstant(Q.costPerHour),
        scalarInstant(Q.avgQuality),
      ]);
      setMetrics({
        rps: rps != null ? rps.toFixed(2) : null,
        p95: p95 != null ? Math.round(p95) : null,
        hit: hit != null ? hit.toFixed(1) : null,
        cost: cost != null ? cost.toFixed(4) : null,
        quality: quality != null ? quality.toFixed(2) : null,
      });
    } catch {}
    setLoading(false);
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10_000);
    return () => clearInterval(t);
  }, []);

  return (
    <div
      style={{
        background: "var(--bg-gov)",
        borderRadius: "var(--radius)",
        padding: "var(--space-4) var(--space-6)",
        display: "flex",
        gap: "var(--space-8)",
        alignItems: "center",
        flexWrap: "wrap",
        border: "1px solid var(--border-gov)",
      }}
    >
      <MetricCell label="RPS" value={metrics.rps} unit=" req/s" />
      <div style={{ width: 1, height: 28, background: "var(--border-gov)" }} />
      <MetricCell label="P95 Latency" value={metrics.p95} unit=" ms" />
      <div style={{ width: 1, height: 28, background: "var(--border-gov)" }} />
      <MetricCell label="Cache Hit" value={metrics.hit} unit="%" />
      <div style={{ width: 1, height: 28, background: "var(--border-gov)" }} />
      <MetricCell label="Cost / hr" value={metrics.cost} unit=" USD" />
      <div style={{ width: 1, height: 28, background: "var(--border-gov)" }} />
      <MetricCell label="Avg Quality" value={metrics.quality} unit=" / 5" />
      {loading && (
        <span style={{ fontSize: 11, color: "var(--text-gov-3)", marginLeft: "auto" }}>
          Loading Prometheus…
        </span>
      )}
      {!loading && Object.values(metrics).every((v) => v == null) && (
        <span style={{ fontSize: 11, color: "var(--text-gov-3)", marginLeft: "auto" }}>
          PROMETHEUS UNAVAILABLE — metrics not shown
        </span>
      )}
    </div>
  );
}
