/**
 * BudgetBadge — coloured pill for budget class (low/medium/high/critical).
 * Budget class and model are visually distinct governance decisions (§63).
 */
const BUDGET_CONFIG = {
  low:      { color: "#10B981", bg: "rgba(16,185,129,0.12)",  label: "LOW" },
  medium:   { color: "#4F46E5", bg: "rgba(79,70,229,0.12)",   label: "MEDIUM" },
  high:     { color: "#F59E0B", bg: "rgba(245,158,11,0.12)",  label: "HIGH" },
  critical: { color: "#EF4444", bg: "rgba(239,68,68,0.12)",   label: "CRITICAL" },
};

export default function BudgetBadge({ budgetClass, size = "sm" }) {
  const key = (budgetClass || "").toLowerCase();
  const cfg = BUDGET_CONFIG[key] || { color: "#94A3B8", bg: "rgba(148,163,184,0.12)", label: key.toUpperCase() || "—" };
  const fontSize = size === "lg" ? "13px" : size === "md" ? "11px" : "10px";
  const padding = size === "lg" ? "5px 12px" : size === "md" ? "3px 9px" : "2px 7px";

  return (
    <span
      style={{
        display: "inline-block",
        padding,
        borderRadius: "var(--radius-sm)",
        background: cfg.bg,
        color: cfg.color,
        fontSize,
        fontWeight: 700,
        letterSpacing: "0.06em",
        fontFamily: "var(--font-ui)",
        whiteSpace: "nowrap",
        border: `1px solid ${cfg.color}22`,
      }}
      aria-label={`Budget class: ${cfg.label}`}
    >
      {cfg.label}
    </span>
  );
}
