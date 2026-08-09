/**
 * InferaCordon SPA root.
 * Five pages per CLAUDE.md Section 22:
 *   /           → Playground (primary demo page)
 *   /dashboard  → Dashboard (real-time metrics)
 *   /policies   → PolicyManager
 *   /audit      → AuditLog
 *   /health     → SystemHealth
 *
 * Served as static files by FastAPI gateway (no separate frontend server).
 * Build: npm run build → output written to dist/ → mounted at gateway /app/static
 */
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import Playground from "./pages/Playground";
import Dashboard from "./pages/Dashboard";
import PolicyManager from "./pages/PolicyManager";
import AuditLog from "./pages/AuditLog";
import SystemHealth from "./pages/SystemHealth";

export default function App() {
  return (
    <BrowserRouter>
      <nav>
        <NavLink to="/">Playground</NavLink>
        <NavLink to="/dashboard">Dashboard</NavLink>
        <NavLink to="/policies">Policies</NavLink>
        <NavLink to="/audit">Audit Log</NavLink>
        <NavLink to="/health">System Health</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<Playground />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/policies" element={<PolicyManager />} />
        <Route path="/audit" element={<AuditLog />} />
        <Route path="/health" element={<SystemHealth />} />
      </Routes>
    </BrowserRouter>
  );
}
