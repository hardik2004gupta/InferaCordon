/**
 * StatusBadge — colour + icon + label for any system state.
 * Every status has icon + label + colour (never colour-only per §44).
 */
const STATUS_MAP = {
  pass:         { color: "var(--pass)",    bg: "var(--pass-bg)",    label: "PASS",         icon: "✓" },
  flag:         { color: "var(--warn)",    bg: "var(--warn-bg)",    label: "FLAG",         icon: "⚑" },
  block:        { color: "var(--fail)",    bg: "var(--fail-bg)",    label: "BLOCK",        icon: "✗" },
  operational:  { color: "var(--pass)",    bg: "var(--pass-bg)",    label: "OPERATIONAL",  icon: "●" },
  degraded:     { color: "var(--warn)",    bg: "var(--warn-bg)",    label: "DEGRADED",     icon: "◑" },
  unavailable:  { color: "var(--fail)",    bg: "var(--fail-bg)",    label: "UNAVAILABLE",  icon: "○" },
  open:         { color: "var(--fail)",    bg: "var(--fail-bg)",    label: "OPEN",         icon: "⚡" },
  closed:       { color: "var(--pass)",    bg: "var(--pass-bg)",    label: "CLOSED",       icon: "●" },
  pending:      { color: "var(--info)",    bg: "var(--info-bg)",    label: "PENDING",      icon: "○" },
  running:      { color: "var(--info)",    bg: "var(--info-bg)",    label: "RUNNING",      icon: "↻" },
  completed:    { color: "var(--pass)",    bg: "var(--pass-bg)",    label: "COMPLETED",    icon: "✓" },
  failed:       { color: "var(--fail)",    bg: "var(--fail-bg)",    label: "FAILED",       icon: "✗" },
  correct:      { color: "var(--pass)",    bg: "var(--pass-bg)",    label: "CORRECT",      icon: "✓" },
  incorrect:    { color: "var(--fail)",    bg: "var(--fail-bg)",    label: "INCORRECT",    icon: "✗" },
  unverifiable: { color: "var(--warn)",    bg: "var(--warn-bg)",    label: "UNVERIFIABLE", icon: "?" },
  skipped:      { color: "var(--unknown)", bg: "rgba(148,163,184,0.1)", label: "SKIPPED",  icon: "–" },
  high:         { color: "var(--pass)",    bg: "var(--pass-bg)",    label: "HIGH",         icon: "●" },
  low:          { color: "var(--warn)",    bg: "var(--warn-bg)",    label: "LOW",          icon: "◑" },
  unknown:      { color: "var(--unknown)", bg: "rgba(148,163,184,0.1)", label: "UNKNOWN",  icon: "?" },
};

export default function StatusBadge({ status, label, size = "sm" }) {
  const key = (status || "unknown").toLowerCase().replace(/[^a-z]/g, "_");
  const cfg = STATUS_MAP[key] || STATUS_MAP.unknown;
  const displayLabel = label || cfg.label;
  const fontSize = size === "lg" ? "12px" : "10px";
  const padding = size === "lg" ? "4px 10px" : "2px 7px";
  const gap = size === "lg" ? "5px" : "4px";

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap,
        padding,
        borderRadius: "var(--radius-sm)",
        background: cfg.bg,
        color: cfg.color,
        fontSize,
        fontWeight: 600,
        letterSpacing: "0.04em",
        fontFamily: "var(--font-ui)",
        whiteSpace: "nowrap",
      }}
      aria-label={displayLabel}
    >
      <span style={{ fontSize: size === "lg" ? "10px" : "9px", lineHeight: 1 }}>{cfg.icon}</span>
      {displayLabel}
    </span>
  );
}
