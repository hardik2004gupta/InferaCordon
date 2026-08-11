/**
 * PolicyManager — read-only view of all loaded policies per CLAUDE.md §22.4.
 * Fetches from GET /admin/policies (admin-only endpoint).
 * Renders PolicyCard for each policy.
 * Includes YAML inspection panel (read-only, no deploy capability).
 */
import { useState, useEffect } from "react";
import { getPolicies } from "../lib/api.js";
import PolicyCard from "../components/PolicyCard.jsx";

function YamlPanel({ policy }) {
  if (!policy) return null;
  const yaml = JSON.stringify(policy, null, 2);
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
      <div
        style={{
          padding: "var(--space-4) var(--space-5)",
          borderBottom: "1px solid var(--border-gov)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-gov-2)", textTransform: "uppercase" }}>
          Policy Inspection — {policy.policy_id}
        </span>
        <span style={{ fontSize: 10, color: "var(--text-gov-3)" }}>READ ONLY — deployment requires gateway restart</span>
      </div>
      <pre
        style={{
          margin: 0,
          padding: "var(--space-5)",
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          color: "var(--text-gov)",
          lineHeight: 1.7,
          overflowX: "auto",
          maxHeight: 500,
          overflowY: "auto",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {yaml}
      </pre>
    </div>
  );
}

export default function PolicyManager() {
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await getPolicies();
        setPolicies(Array.isArray(data) ? data : []);
        if (data?.length > 0) setSelected(data[0]);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div style={{ padding: "var(--space-8)", maxWidth: 1300, margin: "0 auto", width: "100%" }}>
      <div style={{ marginBottom: "var(--space-6)" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>
          Policy Manager
        </h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Read-only view of all active versioned policies. Governance is only credible when humans can read it.
        </p>
      </div>

      {loading && (
        <div style={{ padding: "var(--space-8)", textAlign: "center", color: "var(--text-secondary)", fontSize: 13 }}>
          Loading policies…
        </div>
      )}

      {error && (
        <div style={{ padding: "var(--space-4) var(--space-5)", background: "rgba(239,68,68,0.08)", border: "1px solid #EF4444", borderRadius: "var(--radius)", color: "#EF4444", fontSize: 12, marginBottom: "var(--space-5)" }}>
          {error.includes("401") ? "UNAUTHORIZED — admin API key required" : `Error loading policies: ${error}`}
        </div>
      )}

      {!loading && !error && policies.length === 0 && (
        <div style={{ padding: "var(--space-8)", textAlign: "center", color: "var(--text-secondary)", fontSize: 13 }}>
          No policies loaded. Ensure policy YAML files are present and the gateway has started.
        </div>
      )}

      {!loading && policies.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: "var(--space-6)", alignItems: "start" }}>
          {/* Policy list */}
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.07em", marginBottom: "var(--space-3)", textTransform: "uppercase" }}>
              ACTIVE POLICIES ({policies.length})
            </div>
            {policies.map((p) => {
              const isSel = selected?.policy_id === p.policy_id;
              return (
                <button
                  key={p.policy_id}
                  onClick={() => setSelected(p)}
                  style={{
                    width: "100%",
                    display: "block",
                    textAlign: "left",
                    padding: "var(--space-4) var(--space-5)",
                    marginBottom: 6,
                    background: isSel ? "var(--bg-gov)" : "var(--bg-surface)",
                    border: `1px solid ${isSel ? "var(--accent)" : "var(--border)"}`,
                    borderRadius: "var(--radius)",
                    cursor: "pointer",
                    transition: "border-color var(--transition), background var(--transition)",
                  }}
                >
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: isSel ? "var(--accent)" : "var(--text-primary)", fontWeight: 600, marginBottom: 3 }}>
                    {p.policy_id}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                    {p.tenant} / {p.domain}
                  </div>
                  <div style={{ fontSize: 9, color: "var(--pass)", fontWeight: 600, marginTop: 4, letterSpacing: "0.04em" }}>
                    v{p.versions?.policy ?? "?"} · ACTIVE
                  </div>
                </button>
              );
            })}
          </div>

          {/* Policy detail */}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
            {selected && <PolicyCard policy={selected} />}
            {selected && <YamlPanel policy={selected} />}
          </div>
        </div>
      )}
    </div>
  );
}
