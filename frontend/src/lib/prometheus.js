/**
 * Prometheus HTTP API query wrapper.
 * Used by Dashboard and MetricsStrip to fetch ic_* metrics.
 * Queries Prometheus at http://localhost:9090 (dev) or via gateway proxy (prod).
 *
 * Per CLAUDE.md Section 18 — all custom metrics use ic_ prefix.
 */

const PROMETHEUS_BASE = "http://localhost:9090";

export async function queryInstant(promql) {
  throw new Error("Implement per CLAUDE.md Section 18 (Week 7)");
}

export async function queryRange(promql, start, end, step) {
  throw new Error("Implement per CLAUDE.md Section 18 (Week 7)");
}

// Convenience queries for ic_ metrics
export const queries = {
  rps: 'rate(ic_request_total[1m])',
  p95Latency: 'histogram_quantile(0.95, rate(ic_latency_seconds_bucket[5m]))',
  cacheHitRate: 'rate(ic_cache_hit_total[5m]) / (rate(ic_cache_hit_total[5m]) + rate(ic_cache_miss_total[5m]))',
  costPerHour: 'rate(ic_cost_usd_total[1h]) * 3600',
  avgQuality: 'histogram_quantile(0.5, rate(ic_quality_score_histogram_bucket[15m]))',
};
