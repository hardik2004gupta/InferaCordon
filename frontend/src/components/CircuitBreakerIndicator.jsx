/**
 * CircuitBreakerIndicator — shows GPU pressure and latency circuit breaker states.
 * Per CLAUDE.md §17: two breakers with CLOSED / OPEN states.
 * Rendered as dark governance card (light-canvas / dark-surface contrast).
 */
export default function CircuitBreakerIndicator({ gpuState = "closed", latencyState = "closed", compact = false }) {
  const breakers = [
    { id: "gpu", label: "GPU PRESSURE", state: gpuState },
    { id: "latency", label: "LATENCY SLO", state: latencyState },
  ];

  if (compact) {
    return (
      <div style={{ display: "flex", gap: 12 }}>
        {breakers.map((b) => (
          <div key={b.id} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: b.state === "open" ? "var(--fail)" : "var(--pass)",
                flexShrink: 0,
              }}
            />
            <span style={{ fontSize: 11, color: "var(--text-gov-2)" }}>
              {b.label}
            </span>
            <span style={{ fontSize: 10, fontWeight: 700, fontFamily: "var(--font-mono)", color: b.state === "open" ? "var(--fail)" : "var(--pass)" }}>
              {b.state.toUpperCase()}
            </span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
      {breakers.map((b) => {
        const isOpen = b.state === "open";
        return (
          <div
            key={b.id}
            style={{
              background: "var(--bg-gov)",
              border: `1px solid ${isOpen ? "rgba(239,68,68,0.3)" : "rgba(16,185,129,0.2)"}`,
              borderRadius: "var(--radius)",
              padding: "var(--space-4)",
            }}
          >
            <div style={{ marginBottom: 8, fontSize: 10, letterSpacing: "0.08em", color: "var(--text-gov-2)", fontWeight: 600 }}>
              {b.label}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: "50%",
                  background: isOpen ? "var(--fail)" : "var(--pass)",
                  boxShadow: isOpen ? "0 0 8px rgba(239,68,68,0.5)" : "0 0 6px rgba(16,185,129,0.4)",
                  flexShrink: 0,
                }}
              />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 16, fontWeight: 500, color: isOpen ? "var(--fail)" : "var(--pass)" }}>
                {b.state.toUpperCase()}
              </span>
            </div>
            <div style={{ marginTop: 6, fontSize: 11, color: "var(--text-gov-3)" }}>
              {isOpen
                ? b.id === "gpu" ? "GPU pressure high — low-priority requests rerouted" : "Latency SLO breached — budget class downgraded"
                : "Normal operation"}
            </div>
          </div>
        );
      })}
    </div>
  );
}
