/**
 * TraceWaterfall — visual timeline of a single request's span hierarchy.
 * Per CLAUDE.md Section 22:
 * - Shows: gateway → guardrail → vllm → verifier spans with timing bars
 * - Derived from Jaeger trace (fetched via Jaeger HTTP API)
 * - Highlights: TTFT, budget ceiling event, verification result
 * Props: { requestId: string, traceId: string }
 */
export default function TraceWaterfall({ requestId, traceId }) {
  throw new Error("Implement per CLAUDE.md Section 22 (Week 8)");
}
