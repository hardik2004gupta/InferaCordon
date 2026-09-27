"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { BudgetBadge } from "@/components/app/BudgetBadge";
import { DEMO_POLICIES } from "@/demo/demoPolicies";
import type { BudgetClass, DemoPolicy } from "@/demo/types";
import { ChevronDown, ChevronRight, FileText, Shield, Gauge, Timer, Database, Tag } from "lucide-react";

function Section({
  title,
  icon: Icon,
  expanded,
  onToggle,
  children,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border-b border-border/30 last:border-0">
      <button
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-center gap-2.5 px-6 py-3.5 text-left transition-colors hover:bg-muted/20"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        )}
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="section-label">{title}</span>
      </button>
      {expanded && <div className="px-6 pb-5">{children}</div>}
    </div>
  );
}

function KV({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="font-mono-tight text-xs">{value}</span>
    </div>
  );
}

function policyToYaml(p: DemoPolicy): string {
  const lines: string[] = [];
  lines.push(`policy_id: ${p.policyId}`);
  lines.push(`tenant: ${p.tenant}`);
  lines.push(`domain: ${p.domain}`);
  lines.push(`schema_version: ${p.schemaVersion}`);
  lines.push("");
  lines.push("budget_profiles:");
  for (const [cls, prof] of Object.entries(p.budgetProfiles)) {
    lines.push(`  ${cls}:`);
    lines.push(`    model: ${prof.model}`);
    lines.push(`    max_reasoning_tokens: ${prof.maxReasoningTokens}`);
    lines.push(`    max_output_tokens: ${prof.maxOutputTokens}`);
    lines.push(`    verification: ${prof.verification}`);
    lines.push(`    context_template: ${prof.contextTemplate}`);
  }
  lines.push("");
  lines.push("complexity_thresholds:");
  lines.push(`  low_max: ${p.complexityThresholds.lowMax}`);
  lines.push(`  medium_max: ${p.complexityThresholds.mediumMax}`);
  lines.push(`  high_max: ${p.complexityThresholds.highMax}`);
  lines.push("");
  lines.push("limits:");
  lines.push(`  requests_per_minute: ${p.limits.requestsPerMinute}`);
  lines.push(`  tokens_per_hour: ${p.limits.tokensPerHour}`);
  lines.push(`  max_cost_per_request_usd: ${p.limits.maxCostPerRequestUsd}`);
  lines.push("");
  lines.push("slo:");
  lines.push(`  p95_latency_ms: ${p.slo.p95LatencyMs}`);
  lines.push(`  quality_floor_score: ${p.slo.qualityFloorScore}`);
  lines.push("");
  lines.push("cache:");
  lines.push(`  enabled: ${p.cache.enabled}`);
  lines.push(`  similarity_threshold: ${p.cache.similarityThreshold}`);
  lines.push(`  ttl_seconds: ${p.cache.ttlSeconds}`);
  lines.push("");
  lines.push("escalation:");
  lines.push(`  enabled: ${p.escalation.enabled}`);
  lines.push(`  max_retries: ${p.escalation.maxRetries}`);
  lines.push("");
  lines.push("versions:");
  lines.push(`  policy: ${p.versions.policy}`);
  lines.push(`  system_prompt: ${p.versions.systemPrompt}`);
  lines.push(`  complexity_scorer: ${p.versions.complexityScorer}`);
  lines.push(`  guardrail_model: ${p.versions.guardrailModel}`);
  lines.push(`  injection_model: ${p.versions.injectionModel}`);
  lines.push(`  verifier: ${p.versions.verifier}`);
  return lines.join("\n");
}

export default function PoliciesPage() {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(["budget"])
  );
  const [showYaml, setShowYaml] = useState(false);

  const policy = DEMO_POLICIES[selectedIdx];

  const toggle = (id: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="flex flex-col lg:flex-row gap-6 min-h-0">
      {/* Mobile: policy dropdown */}
      <div className="lg:hidden">
        <select
          value={selectedIdx}
          onChange={(e) => {
            setSelectedIdx(Number(e.target.value));
            setShowYaml(false);
          }}
          className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-[#3730A3]/30"
        >
          {DEMO_POLICIES.map((p, i) => (
            <option key={p.policyId} value={i}>
              {p.policyId} - {p.tenant}/{p.domain} (v{p.versions.policy})
            </option>
          ))}
        </select>
      </div>

      {/* Left: policy list (desktop only) */}
      <div className="hidden lg:block w-[240px] flex-shrink-0 space-y-1.5">
        <h3 className="section-label mb-3">Loaded Policies</h3>
        {DEMO_POLICIES.map((p, i) => (
          <button
            key={p.policyId}
            onClick={() => {
              setSelectedIdx(i);
              setShowYaml(false);
            }}
            className={`w-full rounded-lg border bg-card p-3 text-left transition-colors ${
              i === selectedIdx
                ? "border-l-2 border-l-[#3730A3] border-t-border border-r-border border-b-border"
                : "border-border hover:bg-muted/30"
            }`}
          >
            <div className="text-sm font-medium">{p.policyId}</div>
            <div className="mt-1 flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <span>{p.tenant}</span>
              <span className="text-border">/</span>
              <span>{p.domain}</span>
            </div>
            <div className="mt-1.5 font-mono-tight text-[10px] text-muted-foreground">
              v{p.versions.policy}
            </div>
          </button>
        ))}
      </div>

      {/* Right: detail */}
      <div className="flex-1 min-w-0 rounded-lg border border-border bg-card">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/50 px-6 py-5">
          <div>
            <h2 className="text-base font-semibold">{policy.policyId}</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {policy.tenant} / {policy.domain}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="font-mono-tight text-[10px]">
              v{policy.versions.policy}
            </Badge>
            <Badge variant="secondary" className="text-[10px]">
              schema v{policy.schemaVersion}
            </Badge>
            <button
              onClick={() => setShowYaml(!showYaml)}
              className={`ml-2 flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[10px] font-medium transition-colors ${
                showYaml
                  ? "border-[#3730A3]/30 bg-[#3730A3]/5 text-[#3730A3]"
                  : "border-border text-muted-foreground hover:bg-muted/30"
              }`}
            >
              <FileText className="h-3 w-3" />
              YAML
            </button>
          </div>
        </div>

        {showYaml ? (
          <div className="p-6">
            <pre className="overflow-x-auto rounded-lg bg-muted/40 p-5 text-[11px] leading-relaxed font-mono-tight text-foreground/80">
              {policyToYaml(policy)}
            </pre>
          </div>
        ) : (
          <>
            {/* Budget Profiles */}
            <Section
              title="Budget Profiles"
              icon={Gauge}
              expanded={expandedSections.has("budget")}
              onToggle={() => toggle("budget")}
            >
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-muted-foreground">
                      <th className="pb-2.5 pr-4 font-medium">Class</th>
                      <th className="pb-2.5 pr-4 font-medium">Model</th>
                      <th className="pb-2.5 pr-4 text-right font-medium">Reasoning</th>
                      <th className="pb-2.5 pr-4 text-right font-medium">Output</th>
                      <th className="pb-2.5 pr-4 font-medium">Verification</th>
                      <th className="pb-2.5 font-medium">Template</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(
                      Object.entries(policy.budgetProfiles) as [
                        BudgetClass,
                        (typeof policy.budgetProfiles)[BudgetClass],
                      ][]
                    ).map(([cls, prof]) => (
                      <tr key={cls} className="border-t border-border/30">
                        <td className="py-2.5 pr-4">
                          <BudgetBadge budgetClass={cls} />
                        </td>
                        <td className="py-2.5 pr-4 font-mono-tight">{prof.model}</td>
                        <td className="py-2.5 pr-4 text-right font-mono-tight">
                          {prof.maxReasoningTokens}
                        </td>
                        <td className="py-2.5 pr-4 text-right font-mono-tight">
                          {prof.maxOutputTokens}
                        </td>
                        <td className="py-2.5 pr-4 font-mono-tight text-muted-foreground">
                          {prof.verification}
                        </td>
                        <td className="py-2.5 font-mono-tight text-muted-foreground">
                          {prof.contextTemplate}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-4 rounded-md bg-muted/30 px-3 py-2 text-[10px] font-mono-tight text-muted-foreground">
                Complexity thresholds: low &le; {policy.complexityThresholds.lowMax} | medium &le;{" "}
                {policy.complexityThresholds.mediumMax} | high &le;{" "}
                {policy.complexityThresholds.highMax} | critical &gt;{" "}
                {policy.complexityThresholds.highMax}
              </div>
            </Section>

            {/* Guardrails */}
            <Section
              title="Guardrails"
              icon={Shield}
              expanded={expandedSections.has("guardrails")}
              onToggle={() => toggle("guardrails")}
            >
              <div className="grid gap-x-8 gap-y-0 sm:grid-cols-2">
                <KV label="PII Redaction" value="standard" />
                <KV label="Injection Check" value="conditional" />
                <KV label="Safety Check" value="conditional" />
                <KV label="Output Safety" value="async" />
              </div>
            </Section>

            {/* Rate Limits */}
            <Section
              title="Rate Limits"
              icon={Timer}
              expanded={expandedSections.has("limits")}
              onToggle={() => toggle("limits")}
            >
              <div className="grid gap-x-8 gap-y-0 sm:grid-cols-2">
                <KV label="Requests / min" value={policy.limits.requestsPerMinute} />
                <KV label="Tokens / hour" value={policy.limits.tokensPerHour.toLocaleString()} />
                <KV label="Max cost / request" value={`$${policy.limits.maxCostPerRequestUsd}`} />
              </div>
            </Section>

            {/* SLO */}
            <Section
              title="SLO"
              icon={Gauge}
              expanded={expandedSections.has("slo")}
              onToggle={() => toggle("slo")}
            >
              <div className="grid gap-x-8 gap-y-0 sm:grid-cols-2">
                <KV label="P95 Latency" value={`${policy.slo.p95LatencyMs}ms`} />
                <KV label="Quality Floor" value={policy.slo.qualityFloorScore} />
              </div>
            </Section>

            {/* Cache / Escalation */}
            <Section
              title="Cache / Escalation"
              icon={Database}
              expanded={expandedSections.has("cache")}
              onToggle={() => toggle("cache")}
            >
              <div className="grid gap-x-8 gap-y-0 sm:grid-cols-2">
                <KV label="Cache" value={policy.cache.enabled ? "enabled" : "disabled"} />
                <KV label="Similarity Threshold" value={policy.cache.similarityThreshold} />
                <KV label="TTL" value={`${policy.cache.ttlSeconds}s`} />
                <KV label="Escalation" value={policy.escalation.enabled ? "enabled" : "disabled"} />
                <KV label="Max Retries" value={policy.escalation.maxRetries} />
              </div>
            </Section>

            {/* Version Identifiers */}
            <Section
              title="Version Identifiers"
              icon={Tag}
              expanded={expandedSections.has("versions")}
              onToggle={() => toggle("versions")}
            >
              <div className="grid gap-x-8 gap-y-0 sm:grid-cols-2">
                {Object.entries(policy.versions).map(([k, v]) => (
                  <KV key={k} label={k} value={String(v)} />
                ))}
              </div>
            </Section>
          </>
        )}
      </div>
    </div>
  );
}
