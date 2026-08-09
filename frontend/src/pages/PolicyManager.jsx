/**
 * PolicyManager page — view active policies per tenant/domain.
 * Per CLAUDE.md Section 22:
 * - Lists all tenants and domains with their active policy version
 * - PolicyCard per tenant/domain: budget profiles, limits, SLO, guardrail config
 * - Read-only in MVP (policy edits require YAML + restart)
 * - Data: GET /v1/policy/{tenant_id}/{domain}
 */
export default function PolicyManager() {
  throw new Error("Implement per CLAUDE.md Section 22 (Week 7)");
}
