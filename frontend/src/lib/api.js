/**
 * Gateway API client — all gateway HTTP calls go through this module.
 *
 * In production: same-origin (static files served by FastAPI gateway).
 * In dev: Vite proxy forwards /v1, /admin, /audit to http://localhost:8000.
 *
 * Per CLAUDE.md §7: exact API contracts implemented here.
 * No business logic — frontend displays; backend governs.
 */

const API_KEY_HEADER = () => {
  const key = sessionStorage.getItem("ic_api_key") || "";
  return key ? { Authorization: `Bearer ${key}` } : {};
};

async function _fetch(path, options = {}) {
  const res = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...API_KEY_HEADER(),
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || body.error || detail;
    } catch {}
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

// ── API key management ───────────────────────────────────────────────────────

export function setApiKey(key) {
  if (key) sessionStorage.setItem("ic_api_key", key);
  else sessionStorage.removeItem("ic_api_key");
}

export function getApiKey() {
  return sessionStorage.getItem("ic_api_key") || "";
}

// ── Health / Readiness ───────────────────────────────────────────────────────

export async function getHealth() {
  return _fetch("/v1/health");
}

export async function getReadiness() {
  return _fetch("/v1/readiness");
}

export async function getStatus() {
  return _fetch("/v1/status");
}

// ── Inference ────────────────────────────────────────────────────────────────

/**
 * POST /v1/infer
 * @param {object} params
 * @param {string} params.prompt
 * @param {string} params.tenant_id
 * @param {string} params.domain
 * @param {string|null} params.budget_override
 * @param {object|null} params.response_schema
 * @returns {Promise<InferResponse>}
 */
export async function postInfer({ prompt, tenant_id, domain, budget_override, response_schema }) {
  return _fetch("/v1/infer", {
    method: "POST",
    body: JSON.stringify({
      prompt,
      tenant_id,
      domain,
      budget_override: budget_override || undefined,
      response_schema: response_schema || undefined,
      stream: false,
    }),
  });
}

// ── Admin — policies ─────────────────────────────────────────────────────────

export async function getPolicies() {
  return _fetch("/admin/policies");
}

// ── Admin — failure injection (DEMO_MODE only) ───────────────────────────────

export async function injectFailure(failure_type) {
  return _fetch("/admin/inject-failure", {
    method: "POST",
    body: JSON.stringify({ failure_type }),
  });
}

// ── Audit log ────────────────────────────────────────────────────────────────

/**
 * GET /audit/records
 * @param {object} filters
 * @param {string?} filters.tenant_id
 * @param {string?} filters.budget_class
 * @param {string?} filters.record_type  "decision" | "outcome"
 * @param {number}  filters.limit
 * @param {number}  filters.offset
 */
export async function getAuditRecords(filters = {}) {
  const params = new URLSearchParams();
  if (filters.tenant_id) params.set("tenant_id", filters.tenant_id);
  if (filters.budget_class) params.set("budget_class", filters.budget_class);
  if (filters.record_type) params.set("record_type", filters.record_type);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.offset != null) params.set("offset", String(filters.offset));
  const qs = params.toString();
  return _fetch(`/audit/records${qs ? `?${qs}` : ""}`);
}

// ── Evaluation jobs ──────────────────────────────────────────────────────────

export async function getEvalJobs({ limit = 50, status } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) params.set("status", status);
  return _fetch(`/v1/eval-jobs?${params}`);
}
