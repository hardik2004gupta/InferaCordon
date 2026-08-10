/**
 * InferaCordon SPA root.
 * Light canvas + dark governance surfaces visual identity.
 *
 * Five pages per CLAUDE.md §22:
 *   /           → Playground
 *   /dashboard  → Dashboard
 *   /policies   → Policy Manager
 *   /audit      → Audit Log Explorer
 *   /health     → System Health
 *
 * Served as static files by FastAPI gateway (no separate frontend server).
 */
import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, NavLink, useLocation } from "react-router-dom";
import Playground from "./pages/Playground.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import PolicyManager from "./pages/PolicyManager.jsx";
import AuditLog from "./pages/AuditLog.jsx";
import SystemHealth from "./pages/SystemHealth.jsx";
import { getHealth } from "./lib/api.js";

const NAV_ITEMS = [
  { to: "/",          label: "Playground",    icon: "⬡", desc: "Live inference" },
  { to: "/dashboard", label: "Dashboard",     icon: "◈", desc: "Metrics" },
  { to: "/policies",  label: "Policies",      icon: "◉", desc: "Governance" },
  { to: "/audit",     label: "Audit Log",     icon: "◧", desc: "Records" },
  { to: "/health",    label: "System Health", icon: "◎", desc: "Status" },
];

function Sidebar({ systemOk }) {
  const location = useLocation();

  return (
    <nav
      style={{
        width: 240,
        flexShrink: 0,
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        position: "sticky",
        top: 0,
        overflow: "hidden",
      }}
      aria-label="Primary navigation"
    >
      {/* Wordmark */}
      <div
        style={{
          padding: "var(--space-5) var(--space-6)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
          InferaCordon
        </div>
        <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2, letterSpacing: "0.04em" }}>
          AI INFERENCE GOVERNANCE
        </div>
      </div>

      {/* Navigation items */}
      <div style={{ flex: 1, padding: "var(--space-4) var(--space-3)", overflowY: "auto" }}>
        {NAV_ITEMS.map((item) => {
          const active = item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-3)",
                padding: "var(--space-3) var(--space-3)",
                borderRadius: "var(--radius)",
                marginBottom: 2,
                textDecoration: "none",
                color: active ? "var(--accent)" : "var(--text-secondary)",
                background: active ? "var(--accent-glow)" : "transparent",
                fontWeight: active ? 600 : 400,
                transition: "background var(--transition), color var(--transition)",
              }}
            >
              <span style={{ fontSize: 14, width: 18, textAlign: "center", lineHeight: 1, flexShrink: 0 }}>
                {item.icon}
              </span>
              <div>
                <div style={{ fontSize: 13 }}>{item.label}</div>
                <div style={{ fontSize: 10, color: active ? "var(--accent-light)" : "var(--text-muted)", marginTop: 1 }}>
                  {item.desc}
                </div>
              </div>
            </NavLink>
          );
        })}
      </div>

      {/* Status indicator */}
      <div
        style={{
          padding: "var(--space-4) var(--space-5)",
          borderTop: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
        }}
      >
        <div
          style={{
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: systemOk === null ? "var(--unknown)" : systemOk ? "var(--pass)" : "var(--fail)",
            flexShrink: 0,
          }}
        />
        <span style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 500 }}>
          {systemOk === null ? "CHECKING…" : systemOk ? "ALL SYSTEMS OPERATIONAL" : "SYSTEM UNAVAILABLE"}
        </span>
      </div>
    </nav>
  );
}

function AppShell() {
  const [systemOk, setSystemOk] = useState(null);

  useEffect(() => {
    async function check() {
      try {
        await getHealth();
        setSystemOk(true);
      } catch {
        setSystemOk(false);
      }
    }
    check();
    const t = setInterval(check, 30_000);
    return () => clearInterval(t);
  }, []);

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--bg-app)" }}>
      <Sidebar systemOk={systemOk} />
      <main style={{ flex: 1, minWidth: 0, overflowY: "auto", display: "flex", flexDirection: "column" }}>
        <Routes>
          <Route path="/" element={<Playground />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/policies" element={<PolicyManager />} />
          <Route path="/audit" element={<AuditLog />} />
          <Route path="/health" element={<SystemHealth />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}
