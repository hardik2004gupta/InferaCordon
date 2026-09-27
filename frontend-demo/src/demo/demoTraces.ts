import type { TraceSpan } from "./types";

export function getTraceForScenario(scenarioId: string): TraceSpan[] {
  switch (scenarioId) {
    case "scenario-simple":
      return [
        { name: "Authentication", startMs: 0, durationMs: 1, status: "ok", color: "var(--color-indigo)" },
        { name: "Trace Context", startMs: 1, durationMs: 1, status: "ok", color: "var(--color-indigo)" },
        { name: "Complexity Scoring", startMs: 2, durationMs: 2, status: "ok", color: "var(--color-cyan)" },
        { name: "Policy Lookup", startMs: 4, durationMs: 1, status: "ok", color: "var(--color-slate)" },
        { name: "Budget Assignment", startMs: 5, durationMs: 1, status: "ok", color: "var(--color-slate)" },
        { name: "PII Redaction", startMs: 6, durationMs: 8, status: "ok", color: "var(--color-indigo)" },
        { name: "Cache Lookup", startMs: 14, durationMs: 4, status: "ok", color: "var(--color-indigo)" },
        { name: "Guardrail Input", startMs: 18, durationMs: 24, status: "ok", color: "var(--color-emerald)" },
        { name: "Inference (Qwen)", startMs: 42, durationMs: 280, status: "ok", color: "var(--color-violet)" },
        { name: "Response", startMs: 322, durationMs: 18, status: "ok", color: "var(--color-indigo)" },
      ];
    case "scenario-complex":
      return [
        { name: "Authentication", startMs: 0, durationMs: 1, status: "ok", color: "var(--color-indigo)" },
        { name: "Trace Context", startMs: 1, durationMs: 1, status: "ok", color: "var(--color-indigo)" },
        { name: "Complexity Scoring", startMs: 2, durationMs: 2, status: "ok", color: "var(--color-cyan)" },
        { name: "Policy Lookup", startMs: 4, durationMs: 1, status: "ok", color: "var(--color-slate)" },
        { name: "Budget Assignment", startMs: 5, durationMs: 1, status: "ok", color: "var(--color-slate)" },
        { name: "PII Redaction", startMs: 6, durationMs: 12, status: "ok", color: "var(--color-indigo)" },
        { name: "Cache Lookup", startMs: 18, durationMs: 5, status: "ok", color: "var(--color-indigo)" },
        { name: "Guardrail Input", startMs: 23, durationMs: 42, status: "ok", color: "var(--color-emerald)" },
        { name: "Inference (DeepSeek)", startMs: 65, durationMs: 2480, status: "ok", color: "var(--color-violet)" },
        { name: "Guardrail Output", startMs: 2545, durationMs: 38, status: "ok", color: "var(--color-emerald)" },
        { name: "Verification", startMs: 2583, durationMs: 22, status: "ok", color: "var(--color-teal)" },
        { name: "Response", startMs: 2605, durationMs: 235, status: "ok", color: "var(--color-indigo)" },
      ];
    case "scenario-escalation":
      return [
        { name: "Authentication", startMs: 0, durationMs: 1, status: "ok", color: "var(--color-indigo)" },
        { name: "Complexity Scoring", startMs: 1, durationMs: 2, status: "ok", color: "var(--color-cyan)" },
        { name: "Policy Lookup", startMs: 3, durationMs: 1, status: "ok", color: "var(--color-slate)" },
        { name: "Budget (medium)", startMs: 4, durationMs: 1, status: "ok", color: "var(--color-slate)" },
        { name: "Guardrail Input", startMs: 5, durationMs: 28, status: "ok", color: "var(--color-emerald)" },
        { name: "Inference #1", startMs: 33, durationMs: 1200, status: "ok", color: "var(--color-violet)" },
        { name: "Verification #1", startMs: 1233, durationMs: 18, status: "error", color: "var(--color-rose)" },
        { name: "Escalation", startMs: 1251, durationMs: 4, status: "warning", color: "var(--color-amber)" },
        { name: "Budget (high)", startMs: 1255, durationMs: 1, status: "ok", color: "var(--color-slate)" },
        { name: "Inference #2", startMs: 1256, durationMs: 2100, status: "ok", color: "var(--color-violet)" },
        { name: "Verification #2", startMs: 3356, durationMs: 15, status: "ok", color: "var(--color-teal)" },
        { name: "Response", startMs: 3371, durationMs: 309, status: "ok", color: "var(--color-indigo)" },
      ];
    case "scenario-guardrail":
      return [
        { name: "Authentication", startMs: 0, durationMs: 1, status: "ok", color: "var(--color-indigo)" },
        { name: "Complexity Scoring", startMs: 1, durationMs: 1, status: "ok", color: "var(--color-cyan)" },
        { name: "Policy Lookup", startMs: 2, durationMs: 1, status: "ok", color: "var(--color-slate)" },
        { name: "PII Redaction", startMs: 3, durationMs: 6, status: "ok", color: "var(--color-indigo)" },
        { name: "Guardrail Input", startMs: 9, durationMs: 115, status: "error", color: "var(--color-rose)" },
      ];
    default:
      return [
        { name: "Authentication", startMs: 0, durationMs: 1, status: "ok", color: "var(--color-indigo)" },
        { name: "Complexity Scoring", startMs: 1, durationMs: 2, status: "ok", color: "var(--color-cyan)" },
        { name: "Policy Lookup", startMs: 3, durationMs: 1, status: "ok", color: "var(--color-slate)" },
        { name: "Inference", startMs: 4, durationMs: 400, status: "ok", color: "var(--color-violet)" },
        { name: "Response", startMs: 404, durationMs: 176, status: "ok", color: "var(--color-indigo)" },
      ];
  }
}
