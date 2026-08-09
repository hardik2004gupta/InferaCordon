/**
 * Gateway API client.
 * All gateway HTTP calls go through this module.
 * Base URL: /api (proxied to http://localhost:8000 in dev via Vite)
 */

const BASE = "";  // Same-origin in production (static served by gateway)

export async function postInfer({ tenantId, domain, prompt, priority = "standard" }) {
  throw new Error("Implement per CLAUDE.md Section 7 (Week 7)");
}

export async function getPolicy(tenantId, domain) {
  throw new Error("Implement per CLAUDE.md Section 7 (Week 7)");
}

export async function getCacheStats() {
  throw new Error("Implement per CLAUDE.md Section 7 (Week 7)");
}

export async function getCircuitBreakers() {
  throw new Error("Implement per CLAUDE.md Section 7 (Week 7)");
}

export async function getHealth() {
  throw new Error("Implement per CLAUDE.md Section 7 (Week 7)");
}
