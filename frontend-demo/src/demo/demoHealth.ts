import type { ServiceHealth } from "./types";

export const DEMO_SERVICES: ServiceHealth[] = [
  { name: "Gateway", status: "operational", version: "0.7.0", requestRate: 42.3, errorRate: 0.2, p95LatencyMs: 3890, lastAlerts: [] },
  { name: "vLLM Serving", status: "operational", version: "0.4.2", requestRate: 38.1, errorRate: 0.0, p95LatencyMs: 3200, lastAlerts: [] },
  { name: "Guardrail Service", status: "operational", version: "1.0.0", requestRate: 42.3, errorRate: 0.1, p95LatencyMs: 85, lastAlerts: [] },
  { name: "Verifier Service", status: "operational", version: "1.0.0", requestRate: 18.7, errorRate: 0.0, p95LatencyMs: 45, lastAlerts: [] },
  { name: "Evaluation Worker", status: "operational", version: "1.0.0", requestRate: 12.4, errorRate: 0.3, p95LatencyMs: 1200, lastAlerts: [] },
  { name: "Semantic Cache", status: "operational", version: "1.0.0", requestRate: 42.3, errorRate: 0.0, p95LatencyMs: 4, lastAlerts: [] },
  { name: "Telemetry", status: "operational", version: "1.0.0", requestRate: 42.3, errorRate: 0.1, p95LatencyMs: 12, lastAlerts: [] },
];

export const DEMO_SYSTEM_EVENTS = [
  { timestamp: "11:42:14", event: "Circuit breaker closed", type: "recovery" as const },
  { timestamp: "11:42:13", event: "GPU pressure normalized", type: "recovery" as const },
  { timestamp: "11:42:10", event: "Routing policy restored", type: "info" as const },
  { timestamp: "11:42:09", event: "Low-priority rerouted to cheap model", type: "warning" as const },
  { timestamp: "11:42:08", event: "GPU pressure CB opened", type: "incident" as const },
  { timestamp: "11:42:06", event: "KV-cache usage: 91.4%", type: "warning" as const },
  { timestamp: "11:38:42", event: "Guardrail timeout (200ms)", type: "warning" as const },
  { timestamp: "11:35:18", event: "Rate limit hit: acme_corp", type: "info" as const },
  { timestamp: "11:30:00", event: "Scheduled health check passed", type: "info" as const },
];
