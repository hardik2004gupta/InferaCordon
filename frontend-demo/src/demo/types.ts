export type BudgetClass = "low" | "medium" | "high" | "critical";
export type StopReason = "natural_boundary" | "budget_exhausted" | "cache_hit" | "fast_path_default";
export type VerificationResult = "correct" | "incorrect" | "unverifiable" | "skipped" | "none";
export type GuardrailResult = "pass" | "flag" | "block" | "degraded";
export type CircuitBreakerState = "closed" | "open";

export interface DemoScenario {
  id: string;
  name: string;
  description: string;
  prompt: string;
  complexityScore: number;
  budgetClass: BudgetClass;
  model: string;
  reasoningTokensAllocated: number;
  reasoningTokensUsed: number;
  outputTokens: number;
  stopReason: StopReason;
  verificationResult: VerificationResult;
  escalationCount: number;
  estimatedCostUsd: number;
  latencyMs: number;
  ttftMs: number;
  cacheHit: boolean;
  guardrailInputResult: GuardrailResult;
  guardrailOutputResult: GuardrailResult;
  policyId: string;
  policyVersion: number;
  confidenceLevel: "high" | "low";
  response: string;
}

export interface DemoMetrics {
  totalRequests: number;
  avgLatencyMs: number;
  p95LatencyMs: number;
  cacheHitRate: number;
  reasoningTokensSaved: number;
  totalReasoningTokens: number;
  verificationPassRate: number;
  escalationRate: number;
  avgCostPerRequest: number;
  costPerCorrectAnswer: number;
  guardrailBlockRate: number;
  activePolicy: string;
  gpuCbState: CircuitBreakerState;
  latencyCbState: CircuitBreakerState;
}

export interface DemoAuditRecord {
  timestamp: string;
  requestId: string;
  tenantId: string;
  domain: string;
  budgetClass: BudgetClass;
  route: string;
  stopReason: StopReason;
  reasoningTokensUsed: number;
  reasoningTokensAllocated: number;
  verificationResult: VerificationResult;
  escalationCount: number;
  outputTokens: number;
  estimatedCostUsd: number;
  latencyMs: number;
  policyId: string;
  policyVersion: number;
  guardrailInputResult: GuardrailResult;
  guardrailOutputResult: GuardrailResult;
  confidenceLevel: "high" | "low";
}

export interface DemoPolicy {
  policyId: string;
  tenant: string;
  domain: string;
  schemaVersion: number;
  budgetProfiles: Record<BudgetClass, {
    model: string;
    maxReasoningTokens: number;
    maxOutputTokens: number;
    verification: string;
    contextTemplate: string;
  }>;
  complexityThresholds: {
    lowMax: number;
    mediumMax: number;
    highMax: number;
  };
  limits: {
    requestsPerMinute: number;
    tokensPerHour: number;
    maxCostPerRequestUsd: number;
  };
  slo: {
    p95LatencyMs: number;
    qualityFloorScore: number;
  };
  cache: {
    enabled: boolean;
    similarityThreshold: number;
    ttlSeconds: number;
  };
  escalation: {
    enabled: boolean;
    maxRetries: number;
  };
  versions: {
    policy: number;
    systemPrompt: string;
    complexityScorer: string;
    guardrailModel: string;
    injectionModel: string;
    verifier: string;
  };
}

export interface TraceSpan {
  name: string;
  startMs: number;
  durationMs: number;
  status: "ok" | "error" | "warning";
  color: string;
  attributes?: Record<string, string | number>;
}

export interface ServiceHealth {
  name: string;
  status: "operational" | "degraded" | "down";
  version: string;
  requestRate: number;
  errorRate: number;
  p95LatencyMs: number;
  lastAlerts: string[];
}
