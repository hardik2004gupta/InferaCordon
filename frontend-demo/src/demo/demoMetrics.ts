import type { DemoMetrics } from "./types";

export const DEMO_METRICS: DemoMetrics = {
  totalRequests: 12_847,
  avgLatencyMs: 1_420,
  p95LatencyMs: 3_890,
  cacheHitRate: 0.234,
  reasoningTokensSaved: 2_841_600,
  totalReasoningTokens: 11_204_800,
  verificationPassRate: 0.924,
  escalationRate: 0.068,
  avgCostPerRequest: 0.0074,
  costPerCorrectAnswer: 0.0091,
  guardrailBlockRate: 0.012,
  activePolicy: "enterprise_standard_v1",
  gpuCbState: "closed",
  latencyCbState: "closed",
};

export const DEMO_BUDGET_DISTRIBUTION = {
  low: 0.34,
  medium: 0.41,
  high: 0.19,
  critical: 0.06,
};

export const DEMO_COST_OVER_TIME = [
  { hour: "00:00", cost: 0.0068, baseline: 0.0112 },
  { hour: "02:00", cost: 0.0071, baseline: 0.0108 },
  { hour: "04:00", cost: 0.0065, baseline: 0.0115 },
  { hour: "06:00", cost: 0.0078, baseline: 0.0121 },
  { hour: "08:00", cost: 0.0082, baseline: 0.0118 },
  { hour: "10:00", cost: 0.0074, baseline: 0.0110 },
  { hour: "12:00", cost: 0.0069, baseline: 0.0114 },
  { hour: "14:00", cost: 0.0076, baseline: 0.0119 },
  { hour: "16:00", cost: 0.0081, baseline: 0.0116 },
  { hour: "18:00", cost: 0.0073, baseline: 0.0113 },
  { hour: "20:00", cost: 0.0070, baseline: 0.0109 },
  { hour: "22:00", cost: 0.0067, baseline: 0.0111 },
];

export const DEMO_LATENCY_OVER_TIME = [
  { hour: "00:00", p50: 890, p95: 3200, p99: 4800 },
  { hour: "02:00", p50: 920, p95: 3400, p99: 5100 },
  { hour: "04:00", p50: 860, p95: 3100, p99: 4600 },
  { hour: "06:00", p50: 1020, p95: 3800, p99: 5400 },
  { hour: "08:00", p50: 1100, p95: 3900, p99: 5600 },
  { hour: "10:00", p50: 940, p95: 3300, p99: 4900 },
  { hour: "12:00", p50: 880, p95: 3150, p99: 4700 },
  { hour: "14:00", p50: 960, p95: 3500, p99: 5200 },
  { hour: "16:00", p50: 1050, p95: 3700, p99: 5500 },
  { hour: "18:00", p50: 910, p95: 3250, p99: 4850 },
  { hour: "20:00", p50: 870, p95: 3050, p99: 4550 },
  { hour: "22:00", p50: 850, p95: 3000, p99: 4500 },
];
