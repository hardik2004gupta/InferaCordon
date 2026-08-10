/**
 * Audit Log Explorer — full-featured explorer per CLAUDE.md §22.5.
 * Data from GET /audit/records with filter params.
 * Two record types per request: decision + outcome (linked by request_id).
 * Columns: timestamp, tenant, request_id, budget_class, route, stop_reason,
 *          reasoning tokens used/allocated, verification result, escalations, cost.
 */
import { useState, useEffect, useCallback } from "react";
import { getAuditRecords } from "../lib/api.js";
import BudgetBadge from "../components/BudgetBadge.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const PAGE_SIZE = 30;

function FilterBar({ filters, setFilters, onRefresh }) {
  const sel = (field) => ({
    value: filters[field] || "",
    onChange: (e) => setFilters((f) => ({ ...f, [field]: e.target.value || undefined, offset: 0 })),
    style: {
      padding: "6px 10px",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-sm)",
      background: "var(--bg-surface)",
      color: "var(--text-primary)",
      fontSize: 12,
      fontFamily: "var(--font-ui)",
      cursor: "pointer",
    },
  });

  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginBottom: "var(--space-5)", padding: "var(--space-4) var(--space-5)", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}>
      <div>
        <label style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.07em", display: "block", marginBottom: 4, textTransform: "uppercase" }}>Tenant</label>
        <select {...sel("tenant_id")}>
          <option value="">All</option>
          <option value="acme_corp">acme_corp</option>
          <option value="demo_tenant">demo_tenant</option>
          <option value="default">default</option>
        </select>
      </div>
      <div>
        <label style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.07em", display: "block", marginBottom: 4, textTransform: "uppercase" }}>Budget Class</label>
        <select {...sel("budget_class")}>
          <option value="">All</option>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
          <option value="critical">critical</option>
        </select>
      </div>
      <div>
        <label style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.07em", display: "block", marginBottom: 4, textTransform: "uppercase" }}>Record Type</label>
        <select {...sel("record_type")}>
          <option value="">All</option>
          <option value="decision">decision</option>
          <option value="outcome">outcome</option>
        </select>
      </div>
      <button
        onClick={onRefresh}
        style={{
          padding: "6px 14px",
          background: "var(--accent)",
          border: "none",
          borderRadius: "var(--radius-sm)",
          color: "#fff",
          fontSize: 11,
          fontWeight: 600,
          cursor: "pointer",
          letterSpacing: "0.04em",
          marginTop: 2,
        }}
      >
        REFRESH
      </button>
    </div>
  );
}

function RecordRow({ record, onSelect, selected }) {
  const isDecision = record.record_type === "decision";
  const isSel = selected?.request_id === record.request_id && selected?.record_type === record.record_type;

  return (
    <tr
      onClick={() => onSelect(record)}
      style={{
        cursor: "pointer",
        background: isSel ? "rgba(79,70,229,0.1)" : "transparent",
        borderBottom: "1px solid var(--border)",
        transition: "background var(--transition)",
      }}
    >
      <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
        {new Date(record.timestamp_iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
      </td>
      <td style={{ padding: "8px 12px", fontSize: 11, color: "var(--text-secondary)" }}>
        {record.tenant_id ?? "—"}
      </td>
      <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)" }}>
        {record.request_id?.slice(0, 12) ?? "—"}
      </td>
      <td style={{ padding: "8px 6px" }}>
        <span style={{
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: "0.06em",
          padding: "2px 6px",
          borderRadius: "var(--radius-sm)",
          background: isDecision ? "rgba(79,70,229,0.12)" : "rgba(16,185,129,0.12)",
          color: isDecision ? "#818CF8" : "#10B981",
          textTransform: "uppercase",
        }}>{record.record_type}</span>
      </td>
      <td style={{ padding: "8px 6px" }}>
        {(record.effective_budget_class || record.budget_class) ? (
          <BudgetBadge budgetClass={record.effective_budget_class || record.budget_class} size="sm" />
        ) : "—"}
      </td>
      <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-secondary)" }}>
        {record.stop_reason ?? record.route ?? "—"}
      </td>
      <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-secondary)" }}>
        {record.reasoning_tokens_used != null ? `${record.reasoning_tokens_used}/${record.reasoning_tokens_allocated ?? "?"}` : "—"}
      </td>
      <td style={{ padding: "8px 6px" }}>
        {record.verification_result ? <StatusBadge status={record.verification_result} /> : "—"}
      </td>
      <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-secondary)" }}>
        {record.escalation_count != null ? record.escalation_count : "—"}
      </td>
      <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-secondary)", textAlign: "right" }}>
        {record.estimated_cost_usd != null ? `$${record.estimated_cost_usd.toFixed(6)}` : record.actual_cost_usd != null ? `$${record.actual_cost_usd.toFixed(6)}` : "—"}
      </td>
    </tr>
  );
}

function RecordDetail({ record }) {
  if (!record) return null;
  return (
    <div style={{ marginTop: "var(--space-5)", background: "var(--bg-gov)", border: "1px solid var(--border-gov)", borderRadius: "var(--radius-lg)", overflow: "hidden", boxShadow: "var(--shadow-gov)" }}>
      <div style={{ padding: "var(--space-4) var(--space-5)", borderBottom: "1px solid var(--border-gov)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-gov-2)", textTransform: "uppercase" }}>
          {record.record_type?.toUpperCase()} RECORD — {record.request_id}
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-gov-3)" }}>
          {record.timestamp_iso}
        </span>
      </div>
      <pre style={{ margin: 0, padding: "var(--space-5)", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-gov)", lineHeight: 1.7, overflowX: "auto", maxHeight: 400, overflowY: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {JSON.stringify(record, null, 2)}
      </pre>
    </div>
  );
}

export default function AuditLog() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ limit: PAGE_SIZE, offset: 0 });
  const [selected, setSelected] = useState(null);
  const [total, setTotal] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAuditRecords(filters);
      const rows = Array.isArray(data) ? data : (data?.records ?? []);
      setRecords(rows);
      setTotal(data?.total ?? rows.length);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { load(); }, [load]);

  const thStyle = {
    padding: "8px 12px",
    textAlign: "left",
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: "0.07em",
    color: "var(--text-muted)",
    textTransform: "uppercase",
    background: "var(--bg-surface)",
    borderBottom: "1px solid var(--border)",
    position: "sticky",
    top: 0,
    zIndex: 1,
  };

  return (
    <div style={{ padding: "var(--space-8)", maxWidth: 1400, margin: "0 auto", width: "100%" }}>
      <div style={{ marginBottom: "var(--space-6)" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>Audit Log Explorer</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Append-only governance records. Every request produces a decision record + outcome record.
        </p>
      </div>

      <FilterBar filters={filters} setFilters={setFilters} onRefresh={load} />

      {error && (
        <div style={{ padding: "var(--space-3) var(--space-4)", background: "rgba(239,68,68,0.08)", border: "1px solid #EF4444", borderRadius: "var(--radius)", color: "#EF4444", fontSize: 12, marginBottom: "var(--space-4)" }}>
          {error}
        </div>
      )}

      <div style={{ overflow: "auto", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", background: "var(--bg-surface)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Timestamp", "Tenant", "Request ID", "Type", "Budget", "Stop/Route", "Tokens Used/Alloc", "Verification", "Escalations", "Cost"].map((h) => (
                <th key={h} style={thStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={10} style={{ padding: "var(--space-6)", textAlign: "center", color: "var(--text-muted)", fontSize: 12 }}>Loading…</td></tr>
            )}
            {!loading && records.length === 0 && (
              <tr><td colSpan={10} style={{ padding: "var(--space-6)", textAlign: "center", color: "var(--text-muted)", fontSize: 12 }}>No records match current filters.</td></tr>
            )}
            {records.map((r, i) => (
              <RecordRow key={`${r.request_id}-${r.record_type}-${i}`} record={r} onSelect={setSelected} selected={selected} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > 0 && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "var(--space-4)" }}>
          <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
            {records.length} records shown · {total} total
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              disabled={!filters.offset}
              onClick={() => setFilters((f) => ({ ...f, offset: Math.max(0, (f.offset ?? 0) - PAGE_SIZE) }))}
              style={{ padding: "6px 14px", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", background: "transparent", color: "var(--text-secondary)", fontSize: 11, cursor: filters.offset ? "pointer" : "not-allowed", opacity: filters.offset ? 1 : 0.4 }}
            >← Prev</button>
            <button
              disabled={records.length < PAGE_SIZE}
              onClick={() => setFilters((f) => ({ ...f, offset: (f.offset ?? 0) + PAGE_SIZE }))}
              style={{ padding: "6px 14px", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", background: "transparent", color: "var(--text-secondary)", fontSize: 11, cursor: records.length >= PAGE_SIZE ? "pointer" : "not-allowed", opacity: records.length >= PAGE_SIZE ? 1 : 0.4 }}
            >Next →</button>
          </div>
        </div>
      )}

      <RecordDetail record={selected} />
    </div>
  );
}
