// Quality data
export const DEMO_QUALITY_DATA = {
  verificationByType: [
    { type: "GSM8K", passed: 94, failed: 6, total: 100 },
    { type: "MATH-500", passed: 89, failed: 11, total: 100 },
    { type: "HumanEval", passed: 42, failed: 8, total: 50 },
    { type: "JSON Schema", passed: 47, failed: 3, total: 50 },
  ],
  qualityTrend: [
    { hour: "00:00", score: 3.8 },
    { hour: "02:00", score: 3.9 },
    { hour: "04:00", score: 3.7 },
    { hour: "06:00", score: 4.0 },
    { hour: "08:00", score: 4.1 },
    { hour: "10:00", score: 3.9 },
    { hour: "12:00", score: 3.8 },
    { hour: "14:00", score: 4.0 },
    { hour: "16:00", score: 4.2 },
    { hour: "18:00", score: 3.9 },
    { hour: "20:00", score: 3.8 },
    { hour: "22:00", score: 4.0 },
  ],
  qualityFloor: 3.5,
  escalationsByBudget: [
    { from: "low", to: "medium", count: 0 },
    { from: "medium", to: "high", count: 312 },
    { from: "high", to: "critical", count: 89 },
  ],
};

// Performance data
export const DEMO_PERFORMANCE_DATA = {
  ttftTrend: [
    { hour: "00:00", ttft: 180 },
    { hour: "02:00", ttft: 195 },
    { hour: "04:00", ttft: 170 },
    { hour: "06:00", ttft: 210 },
    { hour: "08:00", ttft: 240 },
    { hour: "10:00", ttft: 200 },
    { hour: "12:00", ttft: 185 },
    { hour: "14:00", ttft: 205 },
    { hour: "16:00", ttft: 230 },
    { hour: "18:00", ttft: 190 },
    { hour: "20:00", ttft: 175 },
    { hour: "22:00", ttft: 168 },
  ],
  gpuUtilization: 72.4,
  kvCacheUtilization: 64.8,
  decodeTokensPerSec: 142.6,
  p50LatencyMs: 940,
  p99LatencyMs: 5200,
};

// Reliability data
export const DEMO_RELIABILITY_DATA = {
  uptime: 99.94,
  totalFailures: 8,
  admissionQueueDepth: 3,
  admissionCeiling: 32,
  recentEvents: [
    { timestamp: "2026-09-27T10:38:00Z", event: "GPU pressure normalized", type: "recovery" as const },
    { timestamp: "2026-09-27T10:35:12Z", event: "Circuit breaker closed", type: "recovery" as const },
    { timestamp: "2026-09-27T10:34:08Z", event: "GPU pressure CB opened", type: "incident" as const },
    { timestamp: "2026-09-27T10:34:06Z", event: "KV-cache usage > 90%", type: "warning" as const },
    { timestamp: "2026-09-27T10:30:00Z", event: "Guardrail timeout (200ms)", type: "warning" as const },
  ],
};

// Governance data
export const DEMO_GOVERNANCE_DATA = {
  policyDistribution: [
    { policy: "enterprise_standard_v1", tenant: "acme_corp", requests: 8241 },
    { policy: "system_default_v1", tenant: "demo_tenant", requests: 4606 },
  ],
  guardrailEvents: [
    { type: "Block", count: 154, rate: 0.012 },
    { type: "Flag", count: 423, rate: 0.033 },
    { type: "Pass", count: 12270, rate: 0.955 },
  ],
  tenantActivity: [
    { tenant: "acme_corp", requests: 8241, cost: 54.82, avgLatency: 1380 },
    { tenant: "demo_tenant", requests: 4606, cost: 38.41, avgLatency: 1490 },
  ],
};

// Cost-specific data
export const DEMO_COST_DATA = {
  costByBudgetClass: [
    { budgetClass: "low", avgCost: 0.0003, volume: 4368 },
    { budgetClass: "medium", avgCost: 0.0068, volume: 5267 },
    { budgetClass: "high", avgCost: 0.0112, volume: 2441 },
    { budgetClass: "critical", avgCost: 0.0198, volume: 771 },
  ],
  tokenSavingsByClass: [
    { budgetClass: "low", saved: 0, allocated: 0 },
    { budgetClass: "medium", saved: 892400, allocated: 2696704 },
    { budgetClass: "high", saved: 1421800, allocated: 2499584 },
    { budgetClass: "critical", saved: 527400, allocated: 1579008 },
  ],
  cacheContribution: {
    totalSaved: 3008,
    estimatedCostSaved: 22.16,
  },
};
