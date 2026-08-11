/**
 * FailureInjectionPanel — ten failure-mode triggers per CLAUDE.md §7.6 + §17.
 * Only rendered when DEMO_MODE=true (signalled by /v1/status response).
 * Each button triggers POST /admin/inject-failure and shows the result.
 */
import { useState } from "react";
import { injectFailure } from "../lib/api.js";

const FAILURES = [
  { id: "complexity_timeout",       label: "Complexity Timeout",      mode: 1, color: "var(--warn)" },
  { id: "gpu_pressure",             label: "GPU Pressure (CB Open)",   mode: 3, color: "var(--fail)" },
  { id: "latency_slo_breach",       label: "Latency SLO Breach",       mode: 4, color: "var(--fail)" },
  { id: "guardrail_timeout",        label: "Guardrail Timeout",        mode: 5, color: "var(--fail)" },
  { id: "output_unsafe",            label: "Output Unsafe Block",      mode: 6, color: "var(--fail)" },
  { id: "rate_limit",               label: "Rate Limit Exhausted",     mode: 8, color: "var(--warn)" },
  { id: "admission_rejected",       label: "Admission Rejected",       mode: 9, color: "var(--warn)" },
  { id: "verifier_unavailable",     label: "Verifier Unavailable",     mode: null, color: "var(--info)" },
  { id: "policy_fallback",          label: "Policy Fallback",          mode: 7, color: "var(--warn)" },
  { id: "fallback_model_unavailable", label: "Fallback Model Down",    mode: 10, color: "var(--fail)" },
];

export default function FailureInjectionPanel() {
  const [results, setResults] = useState({});
  const [injecting, setInjecting] = useState(null);

  async function handleInject(failure_type) {
    setInjecting(failure_type);
    try {
      const result = await injectFailure(failure_type);
      setResults((r) => ({ ...r, [failure_type]: { ok: true, ...result } }));
    } catch (err) {
      setResults((r) => ({ ...r, [failure_type]: { ok: false, error: err.message } }));
    } finally {
      setInjecting(null);
    }
  }

  return (
    <div
      style={{
        background: "var(--bg-gov)",
        border: "1px solid rgba(239,68,68,0.25)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--space-5)",
        boxShadow: "var(--shadow-gov)",
      }}
    >
      <div style={{ marginBottom: "var(--space-4)", display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--fail)", animation: "pulse 2s infinite" }} />
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "var(--fail)", textTransform: "uppercase" }}>
          FAILURE INJECTION — DEMO MODE
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        {FAILURES.map((f) => {
          const res = results[f.id];
          const isActive = injecting === f.id;

          return (
            <div key={f.id}>
              <button
                onClick={() => handleInject(f.id)}
                disabled={isActive}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 12px",
                  background: "var(--bg-gov-2)",
                  border: `1px solid ${f.color}22`,
                  borderRadius: "var(--radius)",
                  cursor: isActive ? "wait" : "pointer",
                  color: f.color,
                  fontSize: 11,
                  fontWeight: 600,
                  fontFamily: "var(--font-ui)",
                  textAlign: "left",
                  transition: "border-color var(--transition), background var(--transition)",
                }}
              >
                {f.mode != null && (
                  <span
                    style={{
                      background: f.color + "22",
                      color: f.color,
                      borderRadius: "var(--radius-sm)",
                      fontSize: 9,
                      fontWeight: 700,
                      padding: "1px 5px",
                      flexShrink: 0,
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    FM{f.mode}
                  </span>
                )}
                <span style={{ flex: 1 }}>{f.label}</span>
                {isActive && <span style={{ fontSize: 9, opacity: 0.6 }}>…</span>}
              </button>
              {res && (
                <div
                  style={{
                    marginTop: 4,
                    fontSize: 10,
                    fontFamily: "var(--font-mono)",
                    color: res.ok ? "var(--pass)" : "var(--fail)",
                    paddingLeft: 4,
                  }}
                >
                  {res.ok ? "✓ INJECTED" : `✗ ${res.error}`}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }`}</style>
    </div>
  );
}
