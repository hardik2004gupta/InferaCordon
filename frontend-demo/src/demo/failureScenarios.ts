export interface FailureScenario {
  id: string;
  name: string;
  group: "Capacity" | "Latency" | "Dependencies" | "Verification" | "Guardrails";
  description: string;
  steps: {
    label: string;
    detail: string;
    status: "trigger" | "detect" | "respond" | "outcome" | "audit";
  }[];
  severity: "critical" | "warning" | "info";
}

export const FAILURE_SCENARIOS: FailureScenario[] = [
  {
    id: "gpu-pressure",
    name: "GPU Pressure",
    group: "Capacity",
    description: "KV-cache utilization exceeds 90% for 2 consecutive scrapes",
    severity: "critical",
    steps: [
      { label: "Trigger", detail: "KV-cache usage: 91.4%", status: "trigger" },
      { label: "Detect", detail: "GPU pressure CB opens", status: "detect" },
      { label: "Response", detail: "Low-priority → cheap model", status: "respond" },
      { label: "Client", detail: "Request served via Qwen2.5-3B", status: "outcome" },
      { label: "Audit", detail: "CB state change recorded", status: "audit" },
    ],
  },
  {
    id: "latency-breach",
    name: "P99 TTFT SLO Breach",
    group: "Latency",
    description: "P99 TTFT exceeds SLO for 3 consecutive 30s windows",
    severity: "warning",
    steps: [
      { label: "Trigger", detail: "P99 TTFT: 4,800ms > 4,000ms SLO", status: "trigger" },
      { label: "Detect", detail: "Latency CB opens after 3 windows", status: "detect" },
      { label: "Response", detail: "Budget class downgraded by one level", status: "respond" },
      { label: "Client", detail: "Requests served at lower budget", status: "outcome" },
      { label: "Audit", detail: "Latency CB state recorded", status: "audit" },
    ],
  },
  {
    id: "guardrail-timeout",
    name: "Guardrail Service Timeout",
    group: "Dependencies",
    description: "Guardrail service does not respond within 200ms",
    severity: "critical",
    steps: [
      { label: "Trigger", detail: "Guardrail HTTP timeout (200ms)", status: "trigger" },
      { label: "Detect", detail: "Gateway timeout handler", status: "detect" },
      { label: "Response", detail: "Conservative block applied", status: "respond" },
      { label: "Client", detail: "503 returned to client", status: "outcome" },
      { label: "Audit", detail: "Guardrail timeout event logged", status: "audit" },
    ],
  },
  {
    id: "complexity-timeout",
    name: "Complexity Scorer Timeout",
    group: "Latency",
    description: "Complexity scorer exceeds 5ms deadline",
    severity: "info",
    steps: [
      { label: "Trigger", detail: "Scorer: 6.2ms > 5ms deadline", status: "trigger" },
      { label: "Detect", detail: "Pipeline deadline timer", status: "detect" },
      { label: "Response", detail: "Fast-path: default medium class", status: "respond" },
      { label: "Client", detail: "Request continues normally", status: "outcome" },
      { label: "Audit", detail: "fast_path_used: true", status: "audit" },
    ],
  },
  {
    id: "verification-failure",
    name: "Verification Failure",
    group: "Verification",
    description: "Output verification fails, triggering escalation",
    severity: "warning",
    steps: [
      { label: "Trigger", detail: "JSON schema validation failed", status: "trigger" },
      { label: "Detect", detail: "Verifier returns passed: false", status: "detect" },
      { label: "Response", detail: "Escalation: medium → high budget", status: "respond" },
      { label: "Client", detail: "Retry at higher budget class", status: "outcome" },
      { label: "Audit", detail: "escalation_count: 1 recorded", status: "audit" },
    ],
  },
  {
    id: "injection-detected",
    name: "Injection Attempt Detected",
    group: "Guardrails",
    description: "DeBERTa injection classifier flags input",
    severity: "warning",
    steps: [
      { label: "Trigger", detail: "Injection score: 0.92 > 0.7 threshold", status: "trigger" },
      { label: "Detect", detail: "Guardrail input check", status: "detect" },
      { label: "Response", detail: "System prompt augmented", status: "respond" },
      { label: "Client", detail: "Request flagged, continues with caution", status: "outcome" },
      { label: "Audit", detail: "Injection flag event recorded", status: "audit" },
    ],
  },
  {
    id: "safety-block",
    name: "Safety Classification Block",
    group: "Guardrails",
    description: "Llama Guard classifies output as unsafe",
    severity: "critical",
    steps: [
      { label: "Trigger", detail: "Output classified: unsafe (0.94 confidence)", status: "trigger" },
      { label: "Detect", detail: "Output guardrail check", status: "detect" },
      { label: "Response", detail: "Structured refusal returned", status: "respond" },
      { label: "Client", detail: "Refusal with reference ID", status: "outcome" },
      { label: "Audit", detail: "Safety block event recorded", status: "audit" },
    ],
  },
  {
    id: "rate-limit",
    name: "Rate Limit Exhausted",
    group: "Capacity",
    description: "Tenant exceeds requests_per_minute limit",
    severity: "warning",
    steps: [
      { label: "Trigger", detail: "Token bucket empty (60 RPM)", status: "trigger" },
      { label: "Detect", detail: "Rate limiter check", status: "detect" },
      { label: "Response", detail: "429 with retry_after_seconds", status: "respond" },
      { label: "Client", detail: "429 response with 14s retry", status: "outcome" },
      { label: "Audit", detail: "Rate limit event recorded", status: "audit" },
    ],
  },
];
