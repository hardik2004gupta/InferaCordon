/**
 * Playground — primary demo interface. Per CLAUDE.md §22.2 + Phase 10 §37.
 * Split layout: left 60% (request + result), right 40% (trace waterfall).
 * Shows full governance metadata from InferResponse.
 * All data from POST /v1/infer — no fabricated values.
 */
import { useState } from "react";
import { postInfer, getApiKey, setApiKey } from "../lib/api.js";
import TraceWaterfall from "../components/TraceWaterfall.jsx";
import BudgetBadge from "../components/BudgetBadge.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const JAEGER_URL = import.meta.env.VITE_JAEGER_URL || "http://localhost:16686";

const PIPELINE_STAGES = [
  "Complexity",
  "Policy Lookup",
  "Budget Assignment",
  "Guardrail (input)",
  "Cache Check",
  "Admission",
  "Inference",
  "Guardrail (output)",
  "Verification",
  "Response",
];

function PageHeader() {
  return (
    <div style={{ marginBottom: "var(--space-6)" }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>
        Inference Playground
      </h1>
      <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
        Submit governed inference requests and inspect every governance decision.
      </p>
    </div>
  );
}

function ApiKeyInput() {
  const [key, setKey] = useState(getApiKey());
  const [saved, setSaved] = useState(false);

  function save() {
    setApiKey(key.trim());
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  return (
    <div
      style={{
        marginBottom: "var(--space-5)",
        display: "flex",
        gap: 8,
        alignItems: "center",
        padding: "var(--space-3) var(--space-4)",
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
      }}
    >
      <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600, letterSpacing: "0.04em", flexShrink: 0 }}>
        API KEY
      </span>
      <input
        type="password"
        value={key}
        onChange={(e) => setKey(e.target.value)}
        placeholder="Bearer token (from tenants.yaml)"
        onKeyDown={(e) => e.key === "Enter" && save()}
        style={{
          flex: 1,
          border: "none",
          outline: "none",
          background: "transparent",
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          color: "var(--text-primary)",
        }}
        aria-label="API key"
      />
      <button
        onClick={save}
        style={{
          padding: "4px 12px",
          background: saved ? "var(--pass-bg)" : "var(--accent-glow)",
          border: `1px solid ${saved ? "var(--pass)" : "var(--accent)"}`,
          borderRadius: "var(--radius-sm)",
          color: saved ? "var(--pass)" : "var(--accent)",
          fontSize: 11,
          fontWeight: 600,
          cursor: "pointer",
          flexShrink: 0,
        }}
      >
        {saved ? "SAVED ✓" : "SET"}
      </button>
    </div>
  );
}

function RequestForm({ onResult, loading, setLoading, setStage }) {
  const [prompt, setPrompt] = useState("");
  const [tenantId, setTenantId] = useState("acme_corp");
  const [domain, setDomain] = useState("general_qa");
  const [budgetOverride, setBudgetOverride] = useState("");
  const [error, setError] = useState(null);

  const charCount = prompt.length;
  const tokenEst = Math.round(charCount / 4);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setError(null);
    setLoading(true);
    setStage("Complexity");

    try {
      const stageTimer = setInterval(() => {
        setStage((s) => {
          const idx = PIPELINE_STAGES.indexOf(s);
          return idx < PIPELINE_STAGES.length - 2 ? PIPELINE_STAGES[idx + 1] : s;
        });
      }, 180);

      const result = await postInfer({
        prompt: prompt.trim(),
        tenant_id: tenantId,
        domain,
        budget_override: budgetOverride || null,
      });

      clearInterval(stageTimer);
      setStage("Response");
      onResult(result);
    } catch (err) {
      setError(err.message || "Request failed");
      setStage(null);
    } finally {
      setLoading(false);
    }
  }

  const selectStyle = {
    padding: "var(--space-2) var(--space-3)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-sm)",
    background: "var(--bg-surface)",
    color: "var(--text-primary)",
    fontSize: 12,
    fontFamily: "var(--font-ui)",
    cursor: "pointer",
  };

  return (
    <form onSubmit={handleSubmit}>
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Enter your prompt here. InferaCordon will score complexity, select a budget class, route to the appropriate model, check guardrails, and verify the answer."
        rows={6}
        style={{
          width: "100%",
          padding: "var(--space-4)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          background: "var(--bg-surface)",
          color: "var(--text-primary)",
          fontSize: 13,
          fontFamily: "var(--font-ui)",
          resize: "vertical",
          outline: "none",
          lineHeight: 1.6,
          transition: "border-color var(--transition)",
        }}
        onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
        onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
        aria-label="Inference prompt"
      />
      <div style={{ marginTop: 6, marginBottom: "var(--space-4)", display: "flex", justifyContent: "flex-end" }}>
        <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
          ~{tokenEst} tokens
        </span>
      </div>

      <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap", marginBottom: "var(--space-4)" }}>
        <div>
          <label style={{ fontSize: 10, fontWeight: 600, color: "var(--text-muted)", letterSpacing: "0.04em", display: "block", marginBottom: 4 }}>
            TENANT
          </label>
          <select value={tenantId} onChange={(e) => setTenantId(e.target.value)} style={selectStyle}>
            <option value="acme_corp">acme_corp</option>
            <option value="demo_tenant">demo_tenant</option>
            <option value="default">default</option>
          </select>
        </div>
        <div>
          <label style={{ fontSize: 10, fontWeight: 600, color: "var(--text-muted)", letterSpacing: "0.04em", display: "block", marginBottom: 4 }}>
            DOMAIN
          </label>
          <select value={domain} onChange={(e) => setDomain(e.target.value)} style={selectStyle}>
            <option value="general_qa">general_qa</option>
            <option value="math">math</option>
            <option value="coding">coding</option>
            <option value="analysis">analysis</option>
          </select>
        </div>
        <div>
          <label style={{ fontSize: 10, fontWeight: 600, color: "var(--text-muted)", letterSpacing: "0.04em", display: "block", marginBottom: 4 }}>
            BUDGET OVERRIDE
          </label>
          <select value={budgetOverride} onChange={(e) => setBudgetOverride(e.target.value)} style={selectStyle}>
            <option value="">Let platform decide</option>
            <option value="low">LOW</option>
            <option value="medium">MEDIUM</option>
            <option value="high">HIGH</option>
            <option value="critical">CRITICAL</option>
          </select>
        </div>
      </div>

      {error && (
        <div
          style={{
            marginBottom: "var(--space-4)",
            padding: "var(--space-3) var(--space-4)",
            background: "var(--fail-bg)",
            border: "1px solid var(--fail)",
            borderRadius: "var(--radius)",
            color: "var(--fail)",
            fontSize: 12,
          }}
        >
          {error.includes("401") ? "UNAUTHORIZED — set a valid API key above" :
           error.includes("503") ? "GATEWAY UNAVAILABLE — vLLM may not be running" :
           error.includes("429") ? "RATE LIMITED — wait and retry" :
           `ERROR: ${error}`}
        </div>
      )}

      <button
        type="submit"
        disabled={loading || !prompt.trim()}
        style={{
          width: "100%",
          padding: "var(--space-3) var(--space-4)",
          background: loading ? "var(--bg-gov-2)" : "var(--accent)",
          border: "none",
          borderRadius: "var(--radius)",
          color: "#fff",
          fontSize: 13,
          fontWeight: 600,
          cursor: loading || !prompt.trim() ? "not-allowed" : "pointer",
          opacity: !prompt.trim() ? 0.6 : 1,
          transition: "background var(--transition)",
          letterSpacing: "0.02em",
        }}
      >
        {loading ? "GOVERNED INFERENCE IN PROGRESS…" : "SUBMIT GOVERNED REQUEST"}
      </button>
    </form>
  );
}

function PipelineProgress({ stage }) {
  if (!stage) return null;
  const idx = PIPELINE_STAGES.indexOf(stage);

  return (
    <div
      style={{
        margin: "var(--space-4) 0",
        padding: "var(--space-4) var(--space-5)",
        background: "var(--bg-gov)",
        borderRadius: "var(--radius)",
        border: "1px solid var(--border-gov)",
      }}
    >
      <div style={{ marginBottom: 10, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-gov-2)" }}>
        GOVERNANCE PIPELINE
      </div>
      <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
        {PIPELINE_STAGES.map((s, i) => {
          const done = i < idx;
          const active = i === idx;
          return (
            <div key={s} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div
                style={{
                  padding: "2px 8px",
                  borderRadius: "var(--radius-sm)",
                  background: done ? "var(--pass-bg)" : active ? "var(--accent-glow)" : "rgba(255,255,255,0.04)",
                  color: done ? "var(--pass)" : active ? "var(--accent-light)" : "var(--text-gov-3)",
                  fontSize: 10,
                  fontWeight: 600,
                  letterSpacing: "0.04em",
                  transition: "all var(--transition)",
                  animation: active ? "pipelinePulse 1s ease infinite" : "none",
                }}
              >
                {done ? "✓ " : active ? "→ " : ""}{s.toUpperCase()}
              </div>
              {i < PIPELINE_STAGES.length - 1 && (
                <div style={{ width: 6, height: 1, background: done ? "var(--pass)" : "rgba(255,255,255,0.1)" }} />
              )}
            </div>
          );
        })}
      </div>
      <style>{`@keyframes pipelinePulse { 0%,100%{opacity:1} 50%{opacity:0.6} }`}</style>
    </div>
  );
}

function GovernanceResult({ result }) {
  if (!result) return null;

  const metrics = [
    { label: "BUDGET CLASS", value: <BudgetBadge budgetClass={result.budget_class} size="md" /> },
    { label: "REASONING TOKENS", value: `${result.reasoning_tokens_used} / ${result.reasoning_tokens_allocated}` },
    { label: "STOP REASON", value: result.stop_reason },
    { label: "VERIFICATION", value: <StatusBadge status={result.verification_result} /> },
    { label: "ESCALATIONS", value: String(result.escalation_count ?? 0) },
    { label: "CONFIDENCE", value: <StatusBadge status={result.confidence_level} /> },
    { label: "COST (USD)", value: result.estimated_cost_usd?.toFixed(6) },
    { label: "LATENCY", value: `${result.latency_ms} ms` },
  ];

  return (
    <div style={{ marginTop: "var(--space-5)" }}>
      {/* Answer */}
      <div
        style={{
          background: "var(--bg-gov)",
          borderRadius: "var(--radius-lg)",
          padding: "var(--space-5)",
          border: "1px solid var(--border-gov)",
          marginBottom: "var(--space-4)",
          boxShadow: "var(--shadow-gov)",
        }}
      >
        <div style={{ marginBottom: 10, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-gov-2)", textTransform: "uppercase" }}>
          Response
        </div>
        <div
          style={{
            fontSize: 13,
            color: "var(--text-gov)",
            lineHeight: 1.7,
            whiteSpace: "pre-wrap",
            fontFamily: "var(--font-ui)",
          }}
        >
          {result.response}
        </div>
      </div>

      {/* Governance metrics strip */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 8,
          marginBottom: "var(--space-4)",
        }}
      >
        {metrics.map(({ label, value }) => (
          <div
            key={label}
            style={{
              background: "var(--bg-gov)",
              border: "1px solid var(--border-gov)",
              borderRadius: "var(--radius)",
              padding: "var(--space-3) var(--space-4)",
            }}
          >
            <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-gov-3)", letterSpacing: "0.07em", marginBottom: 5, textTransform: "uppercase" }}>
              {label}
            </div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-gov)" }}>
              {typeof value === "string" ? value : value}
            </div>
          </div>
        ))}
      </div>

      {/* Decision explanation */}
      <div
        style={{
          background: "var(--bg-gov-2)",
          borderRadius: "var(--radius)",
          padding: "var(--space-4)",
          border: "1px solid var(--border-gov)",
        }}
      >
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-gov-2)", marginBottom: 8, textTransform: "uppercase" }}>
          Governance Decision
        </div>
        <div style={{ fontSize: 12, color: "var(--text-gov)", lineHeight: 1.7 }}>
          <span style={{ fontFamily: "var(--font-mono)", color: "var(--accent-light)" }}>Policy:</span>{" "}
          {result.policy_id} v{result.policy_version}
          {result.policy_fallback_used && " (FALLBACK — default policy applied)"}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-gov)", marginTop: 4 }}>
          <span style={{ fontFamily: "var(--font-mono)", color: "var(--accent-light)" }}>Request ID:</span>{" "}
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{result.request_id}</span>
        </div>
      </div>
    </div>
  );
}

export default function Playground() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState(null);

  return (
    <div style={{ padding: "var(--space-8)", maxWidth: 1400, margin: "0 auto", width: "100%" }}>
      <PageHeader />
      <ApiKeyInput />

      <div style={{ display: "grid", gridTemplateColumns: "60% 1fr", gap: "var(--space-6)", alignItems: "start" }}>
        {/* Left: request + result */}
        <div>
          <RequestForm
            onResult={setResult}
            loading={loading}
            setLoading={setLoading}
            setStage={setStage}
          />
          <PipelineProgress stage={loading ? stage : null} />
          <GovernanceResult result={result} />
        </div>

        {/* Right: trace waterfall */}
        <div style={{ position: "sticky", top: "var(--space-8)" }}>
          <TraceWaterfall result={result} jaegerUrl={JAEGER_URL} />
        </div>
      </div>
    </div>
  );
}
