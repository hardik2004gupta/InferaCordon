/**
 * PolicyCard — structured display of a single policy.
 * Per CLAUDE.md §22.4: four collapsible sections.
 * Read-only. Editing not implemented (requires YAML + restart per §11.4).
 */
import { useState } from "react";
import BudgetBadge from "./BudgetBadge.jsx";

function Section({ title, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ borderTop: "1px solid var(--border-gov)", marginTop: 0 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "10px var(--space-5)",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          color: "var(--text-gov-2)",
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
        }}
        aria-expanded={open}
      >
        <span>{title}</span>
        <span style={{ fontSize: 12, opacity: 0.6 }}>{open ? "−" : "+"}</span>
      </button>
      {open && <div style={{ padding: "4px var(--space-5) var(--space-4)" }}>{children}</div>}
    </div>
  );
}

function KV({ k, v }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
      <span style={{ fontSize: 11, color: "var(--text-gov-2)" }}>{k}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-gov)" }}>{String(v ?? "—")}</span>
    </div>
  );
}

export default function PolicyCard({ policy }) {
  if (!policy) return null;
  const v = policy.versions || {};
  const bp = policy.budget_profiles || {};
  const limits = policy.limits || {};
  const slo = policy.slo || {};
  const cache = policy.cache || {};
  const guardrails = policy.guardrails || {};
  const ct = policy.complexity_thresholds || {};

  return (
    <div
      style={{
        background: "var(--bg-gov)",
        borderRadius: "var(--radius-lg)",
        border: "1px solid var(--border-gov)",
        overflow: "hidden",
        boxShadow: "var(--shadow-gov)",
      }}
    >
      {/* Header */}
      <div style={{ padding: "var(--space-5)", borderBottom: "1px solid var(--border-gov)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 500, color: "var(--text-gov)", marginBottom: 4 }}>
              {policy.policy_id}
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ fontSize: 11, color: "var(--text-gov-2)" }}>
                {policy.tenant} / {policy.domain}
              </span>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--accent-light)", fontWeight: 600 }}>
              v{v.policy ?? "?"}
            </div>
            <div style={{ fontSize: 10, color: "var(--pass)", marginTop: 2, fontWeight: 600 }}>ACTIVE</div>
          </div>
        </div>
      </div>

      <Section title="Budget Profiles" defaultOpen>
        {["low", "medium", "high", "critical"].map((cls) => {
          const p = bp[cls];
          if (!p) return null;
          return (
            <div key={cls} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <BudgetBadge budgetClass={cls} size="sm" />
              <div style={{ flex: 1 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-gov-2)" }}>
                  {p.model} · {p.max_reasoning_tokens}T · {p.max_output_tokens} out
                  {p.verification && p.verification !== "none" && ` · verify:${p.verification}`}
                </span>
              </div>
            </div>
          );
        })}
        <div style={{ marginTop: 8 }}>
          <span style={{ fontSize: 10, color: "var(--text-gov-3)" }}>
            Thresholds: low≤{ct.low_max} · med≤{ct.medium_max} · high≤{ct.high_max} · critical&gt;{ct.high_max}
          </span>
        </div>
      </Section>

      <Section title="Guardrails">
        <KV k="PII Redaction" v={guardrails.pii_redaction} />
        <KV k="Injection Check" v={guardrails.injection_check} />
        <KV k="Safety Check" v={guardrails.safety_check} />
        <KV k="Output Safety" v={guardrails.output_safety} />
      </Section>

      <Section title="Limits & SLOs">
        <KV k="Requests / min" v={limits.requests_per_minute} />
        <KV k="Tokens / hr" v={limits.tokens_per_hour} />
        <KV k="Max cost / req (USD)" v={limits.max_cost_per_request_usd} />
        <KV k="P95 Latency (ms)" v={slo.p95_latency_ms} />
        <KV k="Quality floor" v={slo.quality_floor_score} />
        <KV k="Cache TTL (s)" v={cache.ttl_seconds} />
        <KV k="Cache similarity" v={cache.similarity_threshold} />
      </Section>

      <Section title="Version Identifiers">
        <KV k="Policy" v={v.policy} />
        <KV k="System prompt" v={v.system_prompt} />
        <KV k="Complexity scorer" v={v.complexity_scorer} />
        <KV k="Guardrail model" v={v.guardrail_model} />
        <KV k="Injection model" v={v.injection_model} />
        <KV k="Verifier" v={v.verifier} />
      </Section>
    </div>
  );
}
