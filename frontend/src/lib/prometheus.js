/**
 * Prometheus HTTP API query wrapper.
 * Queries Prometheus at /prometheus (proxied via gateway in prod) or directly at port 9090 in dev.
 *
 * Per CLAUDE.md §18 — all custom metrics use ic_ prefix.
 * NEVER fabricates values — if Prometheus is unreachable, returns null.
 */

// In dev, hit Prometheus directly. In prod, gateway would proxy /prometheus → 9090.
const PROM_BASE =
  typeof window !== "undefined" && window.location.hostname === "localhost"
    ? "http://localhost:9090"
    : "/prometheus";

async function _queryProm(path) {
  try {
    const res = await fetch(`${PROM_BASE}${path}`);
    if (!res.ok) return null;
    const data = await res.json();
    if (data.status !== "success") return null;
    return data.data;
  } catch {
    return null;
  }
}

/**
 * queryInstant — returns a scalar number (first result, first value) or null.
 * Returns null when Prometheus is unavailable or the series is empty.
 */
export async function queryInstant(promql) {
  const data = await _queryProm(
    `/api/v1/query?query=${encodeURIComponent(promql)}`
  );
  const result = data?.result;
  if (!result || result.length === 0) return null;
  const val = parseFloat(result[0].value?.[1]);
  return isNaN(val) ? null : val;
}

/**
 * queryRange — returns flat [[timestamp, value], ...] pairs or [].
 * Uses the first result series. Returns [] when unavailable.
 */
export async function queryRange(promql, start, end, step = 60) {
  const data = await _queryProm(
    `/api/v1/query_range?query=${encodeURIComponent(promql)}&start=${start}&end=${end}&step=${step}`
  );
  const result = data?.result;
  if (!result || result.length === 0) return [];
  return result[0].values ?? [];
}

/**
 * scalarInstant — alias for queryInstant (kept for backward compat).
 */
export async function scalarInstant(promql) {
  return queryInstant(promql);
}

// ── Named ic_ metric queries ──────────────────────────────────────────────────

export const Q = {
  rps:          'sum(rate(ic_request_total[1m]))',
  p95Latency:   'histogram_quantile(0.95, sum by (le) (rate(ic_latency_seconds_bucket[5m]))) * 1000',
  cacheHitRate: '100 * sum(rate(ic_cache_hit_total[5m])) / (sum(rate(ic_cache_hit_total[5m])) + sum(rate(ic_cache_miss_total[5m])))',
  costPerHour:  'sum(rate(ic_cost_usd_total[1h])) * 3600',
  avgQuality:   'histogram_quantile(0.5, sum by (le) (rate(ic_quality_score_histogram_bucket[15m])))',
  gpuCbOpen:    'ic_circuit_breaker_open{breaker_name="gpu_pressure"}',
  latCbOpen:    'ic_circuit_breaker_open{breaker_name="latency"}',
  escalRate:    'sum(rate(ic_escalation_total[5m]))',
  budgetDist:   'sum by (budget_class) (increase(ic_request_total[1h]))',
  guardBlock:   'sum(rate(ic_guardrail_block_total[5m]))',
  fastPath:     'sum(rate(ic_fast_path_activations_total[5m]))',
  reqByBudget:  'sum by (budget_class) (rate(ic_request_total[5m]))',
};
