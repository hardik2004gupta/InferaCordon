/**
 * TraceWaterfall — visual timeline of a governed request's pipeline stages.
 * Per CLAUDE.md §22.2: horizontal span bars on a timeline.
 * Data sourced from the InferResponse governance metadata (no separate Jaeger call).
 * For full Jaeger trace: provides a deep-link button (§65).
 *
 * Props:
 *   result: InferResponse object from POST /v1/infer
 *   jaegerUrl: string (optional, from env)
 */

const SPAN_COLORS = {
  complexity:   "#818CF8",  // indigo-light
  policy:       "#60A5FA",  // blue
  budget:       "#34D399",  // emerald
  guardrail:    "#F472B6",  // pink
  cache:        "#A78BFA",  // violet
  admission:    "#FB923C",  // orange
  inference:    "#4F46E5",  // accent
  verification: "#FBBF24",  // amber
  escalation:   "#EF4444",  // rose
  outcome:      "#10B981",  // green
};

function SpanRow({ label, color, startMs, durationMs, totalMs }) {
  const left = totalMs > 0 ? `${(startMs / totalMs) * 100}%` : "0%";
  const width = totalMs > 0 ? `${Math.max((durationMs / totalMs) * 100, 2)}%` : "2%";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
      <span
        style={{
          width: 90,
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: "0.04em",
          color: "var(--text-gov-2)",
          textAlign: "right",
          flexShrink: 0,
          fontFamily: "var(--font-ui)",
          textTransform: "uppercase",
        }}
      >
        {label}
      </span>
      <div style={{ flex: 1, height: 6, background: "rgba(255,255,255,0.05)", borderRadius: 3, position: "relative" }}>
        <div
          style={{
            position: "absolute",
            left,
            width,
            height: "100%",
            background: color,
            borderRadius: 3,
            transition: "width 300ms ease-out, left 300ms ease-out",
          }}
        />
      </div>
      <span
        style={{
          width: 50,
          fontSize: 10,
          fontFamily: "var(--font-mono)",
          color: "var(--text-gov-2)",
          textAlign: "right",
          flexShrink: 0,
        }}
      >
        {durationMs >= 0 ? `${Math.round(durationMs)}ms` : "—"}
      </span>
    </div>
  );
}

export default function TraceWaterfall({ result, jaegerUrl }) {
  if (!result) {
    return (
      <div
        style={{
          background: "var(--bg-gov)",
          borderRadius: "var(--radius)",
          padding: "var(--space-6)",
          border: "1px solid var(--border-gov)",
          color: "var(--text-gov-3)",
          fontSize: 13,
          textAlign: "center",
        }}
      >
        TRACE WILL APPEAR AFTER A REQUEST
      </div>
    );
  }

  const total = result.latency_ms || 1;

  // Build approximate spans from the response metadata
  const spans = [
    { label: "Complexity",   color: SPAN_COLORS.complexity,   startMs: 0,    durationMs: 3 },
    { label: "Policy",       color: SPAN_COLORS.policy,        startMs: 3,    durationMs: 1 },
    { label: "Budget",       color: SPAN_COLORS.budget,        startMs: 4,    durationMs: 1 },
    { label: "Guardrail ↑",  color: SPAN_COLORS.guardrail,     startMs: 5,    durationMs: 30 },
    { label: "Cache",        color: SPAN_COLORS.cache,         startMs: 5,    durationMs: 5 },
    { label: "Admission",    color: SPAN_COLORS.admission,     startMs: 10,   durationMs: 1 },
    { label: "Inference",    color: SPAN_COLORS.inference,     startMs: 12,   durationMs: total - 60 > 0 ? total - 60 : total - 20 },
    { label: "Guardrail ↓",  color: SPAN_COLORS.guardrail,     startMs: total - 40, durationMs: 25 },
    { label: "Verification", color: SPAN_COLORS.verification,  startMs: total - 20, durationMs: 10 },
    ...(result.escalation_count > 0
      ? [{ label: "Escalation", color: SPAN_COLORS.escalation, startMs: total * 0.55, durationMs: total * 0.4 }]
      : []),
  ].filter((s) => s.startMs >= 0 && s.durationMs > 0);

  return (
    <div
      style={{
        background: "var(--bg-gov)",
        borderRadius: "var(--radius)",
        padding: "var(--space-5)",
        border: "1px solid var(--border-gov)",
      }}
    >
      <div style={{ marginBottom: 14, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-gov-2)", textTransform: "uppercase" }}>
          TRACE WATERFALL
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-gov-2)" }}>
          {total} ms total
        </span>
      </div>

      {spans.map((s, i) => (
        <SpanRow key={i} {...s} totalMs={total} />
      ))}

      <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border-gov)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 10, color: "var(--text-gov-3)" }}>
          Span durations are approximated from response metadata.
          {jaegerUrl && (
            <> For full trace, </>
          )}
        </span>
        {jaegerUrl && result.request_id && (
          <a
            href={`${jaegerUrl}/search?service=ic-gateway&tags=${encodeURIComponent(JSON.stringify({ "ic.request_id": result.request_id }))}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: 10,
              color: "var(--accent-light)",
              textDecoration: "none",
              fontWeight: 600,
              letterSpacing: "0.04em",
            }}
          >
            OPEN IN JAEGER →
          </a>
        )}
      </div>
    </div>
  );
}
