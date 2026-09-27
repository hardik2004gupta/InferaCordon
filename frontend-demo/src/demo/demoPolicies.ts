import type { DemoPolicy } from "./types";

export const DEMO_POLICIES: DemoPolicy[] = [
  {
    policyId: "enterprise_standard_v1",
    tenant: "acme_corp",
    domain: "general_qa",
    schemaVersion: 1,
    budgetProfiles: {
      low: { model: "qwen25-3b", maxReasoningTokens: 0, maxOutputTokens: 256, verification: "none", contextTemplate: "direct" },
      medium: { model: "deepseek-r1-7b", maxReasoningTokens: 512, maxOutputTokens: 512, verification: "verifiable_only", contextTemplate: "step_by_step" },
      high: { model: "deepseek-r1-7b", maxReasoningTokens: 1024, maxOutputTokens: 1024, verification: "required", contextTemplate: "verify_steps" },
      critical: { model: "deepseek-r1-7b", maxReasoningTokens: 2048, maxOutputTokens: 1024, verification: "required", contextTemplate: "verify_steps" },
    },
    complexityThresholds: { lowMax: 3.5, mediumMax: 6.5, highMax: 8.5 },
    limits: { requestsPerMinute: 60, tokensPerHour: 500_000, maxCostPerRequestUsd: 0.05 },
    slo: { p95LatencyMs: 4000, qualityFloorScore: 3.5 },
    cache: { enabled: true, similarityThreshold: 0.92, ttlSeconds: 3600 },
    escalation: { enabled: true, maxRetries: 1 },
    versions: { policy: 1, systemPrompt: "prompt_v2", complexityScorer: "scorer_v1", guardrailModel: "llamaguard_onnx_v1", injectionModel: "deberta_inject_v1", verifier: "verifier_v1" },
  },
  {
    policyId: "system_default_v1",
    tenant: "default",
    domain: "general",
    schemaVersion: 1,
    budgetProfiles: {
      low: { model: "qwen25-3b", maxReasoningTokens: 0, maxOutputTokens: 256, verification: "none", contextTemplate: "direct" },
      medium: { model: "deepseek-r1-7b", maxReasoningTokens: 256, maxOutputTokens: 512, verification: "verifiable_only", contextTemplate: "step_by_step" },
      high: { model: "deepseek-r1-7b", maxReasoningTokens: 512, maxOutputTokens: 512, verification: "required", contextTemplate: "verify_steps" },
      critical: { model: "deepseek-r1-7b", maxReasoningTokens: 1024, maxOutputTokens: 512, verification: "required", contextTemplate: "verify_steps" },
    },
    complexityThresholds: { lowMax: 3.5, mediumMax: 6.5, highMax: 8.5 },
    limits: { requestsPerMinute: 10, tokensPerHour: 50_000, maxCostPerRequestUsd: 0.02 },
    slo: { p95LatencyMs: 6000, qualityFloorScore: 3.0 },
    cache: { enabled: false, similarityThreshold: 0.95, ttlSeconds: 1800 },
    escalation: { enabled: false, maxRetries: 0 },
    versions: { policy: 1, systemPrompt: "prompt_v1", complexityScorer: "scorer_v1", guardrailModel: "llamaguard_onnx_v1", injectionModel: "deberta_inject_v1", verifier: "verifier_v1" },
  },
];
