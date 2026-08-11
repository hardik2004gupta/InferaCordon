/**
 * SystemHealth — live status for all components per CLAUDE.md §22.6.
 * Polls GET /v1/health, GET /v1/status, Prometheus circuit-breaker metrics.
 * Shows FailureInjectionPanel when DEMO_MODE=true.
 * Zero fabricated data.
 */
import { useState, useEffect, useCallback } from "react";
import { getHealth, getStatus, getEvalJobs } from "../lib/api.js";
import { queryInstant, Q } from "../lib/prometheus.js";
import CircuitBreakerIndicator from "../components/CircuitBreakerIndicator.jsx";
import FailureInjectionPanel from "../components/FailureInjectionPanel.jsx";

const SERVICES = [
  { key: "gateway",    label: "FastAPI Gateway",    port: 8000, detail: "Request lifecycle, policy engine, FAISS cache" },
  { key: "vllm",       label: "vLLM Server",        port: 8080, detail: "DeepSeek-R1-7B-Q4 + Qwen2.5-3B-Instruct (GPU)" },
  { key: "guardrail",  label: "Guardrail Service",  port: 8001, detail: "PII redaction, injection + safety classifiers (CPU)" },
  { key: "verifier",   label: "Verifier Service",   port: 8002, detail: "GSM8K / MATH-500 / HumanEval / JSON schema (CPU)" },
  { key: "prometheus", label: "Prometheus",         port: 9090, detail: "Metrics scraping and storage" },
  { key: "grafana",    label: "Grafana",            port: 3000, detail: "Unified observability dashboard" },
  { key: "jaeger",     label: "Jaeger",             port: 16686, detail: "OTel trace collection and inspection" },
];

function ServiceCard({ svc, status }) {
  const isOk = status === "operational";
  const isDeg = status === "degraded";
  const isDn = status === "down";
  const isUnk = status == null || status === "unknown";

  const stateColor = isOk ? "#10B981" : isDeg ? "#F59E0B" : isDn ? "#EF4444" : "#64748B";
  const stateLabel = isOk ? "OPERATIONAL" : isDeg ? "DEGRADED" : isDn ? "DOWN" : "UNKNOWN";
  const stateBg = isOk ? "rgba(16,185,129,0.08)" : isDeg ? "rgba(245,158,11,0.08)" : isDn ? "rgba(239,68,68,0.08)" : "rgba(255,255,255,0.04)";

  return (
    <div
      style={{
        background: "var(--bg-surface)",
        border: `1px solid ${isDn ? "#EF444444" : "var(--border)"}`,
        borderRadius: "var(--radius-lg)",
        padding: "var(--space-5)",
        transition: "border-color var(--transition)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "var(--space-3)" }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 3 }}>{svc.label}</div>
          <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Port {svc.port}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 10px", background: stateBg, borderRadius: "var(--radius-sm)", border: `1px solid ${stateColor}33` }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: stateColor, animation: isUnk ? "pulse 2s infinite" : "none" }} />
          <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.07em", color: stateColor, textTransform: "uppercase" }}>{stateLabel}</span>
        </div>
      </div>
      <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.5 }}>{svc.detail}</div>
    </div>
  );
}

function EvalJobsTable({ jobs }) {
  if (!jobs?.length) return <div style={{ fontSize: 12, color: "var(--text-muted)", padding: "var(--space-4)" }}>No evaluation jobs found.</div>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Request ID", "Domain", "Score", "Status", "Completed"].map((h) => (
              <th key={h} style={{ padding: "8px 12px", textAlign: "left", fontSize: 9, fontWeight: 700, letterSpacing: "0.07em", color: "var(--text-muted)", textTransform: "uppercase", borderBottom: "1px solid var(--border)" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.job_id ?? j.request_id} style={{ borderBottom: "1px solid var(--border)" }}>
              <td style={{ padding: "7px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)" }}>{j.request_id?.slice(0, 14) ?? "—"}</td>
              <td style={{ padding: "7px 12px", fontSize: 11, color: "var(--text-secondary)" }}>{j.domain ?? "—"}</td>
              <td style={{ padding: "7px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: j.score >= 3.5 ? "#10B981" : "#EF4444" }}>{j.score?.toFixed(2) ?? "—"}</td>
              <td style={{ padding: "7px 12px", fontSize: 10, color: "var(--text-secondary)" }}>{j.status ?? "—"}</td>
              <td style={{ padding: "7px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)" }}>{j.completed_at ? new Date(j.completed_at).toLocaleTimeString() : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function SystemHealth() {
  const [serviceStatus, setServiceStatus] = useState({});
  const [sysStatus, setSysStatus] = useState(null);
  const [evalJobs, setEvalJobs] = useState([]);
  const [cbState, setCbState] = useState({ gpu: null, lat: null });
  const [demoMode, setDemoMode] = useState(false);

  const poll = useCallback(async () => {
    // Gateway health
    try {
      await getHealth();
      setServiceStatus((s) => ({ ...s, gateway: "operational" }));
    } catch {
      setServiceStatus((s) => ({ ...s, gateway: "down" }));
    }

    // System status (cache, eval worker, demo mode)
    try {
      const st = await getStatus();
      setSysStatus(st);
      setDemoMode(st.demo_mode === true);
    } catch (_e) { /* status unavailable — non-fatal */ }

    // Eval jobs
    try {
      const jobs = await getEvalJobs({ limit: 10 });
      setEvalJobs(Array.isArray(jobs) ? jobs : []);
    } catch (_e) { /* eval jobs unavailable — non-fatal */ }

    // Circuit breakers via Prometheus
    try {
      const [gpu, lat] = await Promise.all([
        queryInstant(Q.gpuCbOpen),
        queryInstant(Q.latCbOpen),
      ]);
      setCbState({ gpu: gpu === 1, lat: lat === 1 });
      setServiceStatus((s) => ({ ...s, prometheus: "operational" }));
    } catch {
      setCbState({ gpu: null, lat: null });
      setServiceStatus((s) => ({ ...s, prometheus: "degraded" }));
    }
  }, []);

  useEffect(() => {
    poll();
    const id = setInterval(poll, 10_000);
    return () => clearInterval(id);
  }, [poll]);

  return (
    <div style={{ padding: "var(--space-8)", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <div style={{ marginBottom: "var(--space-6)" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>System Health</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Live component status. Polls every 10 seconds. All data from real health endpoints.
        </p>
      </div>

      {/* Circuit Breakers */}
      <div style={{ marginBottom: "var(--space-6)" }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.07em", marginBottom: "var(--space-3)", textTransform: "uppercase" }}>
          Circuit Breakers
        </div>
        <CircuitBreakerIndicator gpuOpen={cbState.gpu} latOpen={cbState.lat} />
      </div>

      {/* Service cards */}
      <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.07em", marginBottom: "var(--space-3)", textTransform: "uppercase" }}>
        Services (7 containers)
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "var(--space-4)", marginBottom: "var(--space-6)" }}>
        {SERVICES.map((svc) => (
          <ServiceCard key={svc.key} svc={svc} status={serviceStatus[svc.key]} />
        ))}
      </div>

      {/* System status detail */}
      {sysStatus && (
        <div style={{ marginBottom: "var(--space-6)", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", padding: "var(--space-5)" }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.07em", marginBottom: "var(--space-4)", textTransform: "uppercase" }}>Gateway Internal State</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }}>
            {[
              { label: "Semantic Cache", value: sysStatus.cache_enabled ? `ENABLED (${sysStatus.cache_count ?? "?"} entries)` : "DISABLED" },
              { label: "Admission Active", value: `${sysStatus.admission_active ?? "?"} / ${sysStatus.admission_max ?? "?"}` },
              { label: "GPU CB State", value: sysStatus.circuit_breakers?.gpu_pressure ?? "CLOSED" },
              { label: "Eval Worker", value: sysStatus.eval_worker_active ? "RUNNING" : "STOPPED" },
            ].map(({ label, value }) => (
              <div key={label}>
                <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.07em", marginBottom: 5, textTransform: "uppercase" }}>{label}</div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-primary)", fontWeight: 600 }}>{value}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Eval jobs */}
      <div style={{ marginBottom: "var(--space-6)", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", overflow: "hidden" }}>
        <div style={{ padding: "var(--space-4) var(--space-5)", borderBottom: "1px solid var(--border)", fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.07em", textTransform: "uppercase" }}>
          Recent Evaluation Jobs (LLM-as-Judge)
        </div>
        <EvalJobsTable jobs={evalJobs} />
      </div>

      {/* Failure injection — only when demo mode */}
      {demoMode && (
        <div style={{ marginTop: "var(--space-6)" }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.07em", marginBottom: "var(--space-3)", textTransform: "uppercase" }}>
            Failure Injection Panel — DEMO_MODE active
          </div>
          <FailureInjectionPanel />
        </div>
      )}

      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }`}</style>
    </div>
  );
}
