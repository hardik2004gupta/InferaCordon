"use client";

import { Fragment, useState, useMemo } from "react";
import { BudgetBadge } from "@/components/app/BudgetBadge";
import { Badge } from "@/components/ui/badge";
import { DEMO_AUDIT_RECORDS } from "@/demo/demoAudit";
import type { BudgetClass, VerificationResult, StopReason, DemoAuditRecord } from "@/demo/types";
import { ChevronDown, ChevronRight, Search } from "lucide-react";

function DetailPanel({ record }: { record: DemoAuditRecord }) {
  const decision = {
    record_type: "decision",
    request_id: record.requestId,
    tenant_id: record.tenantId,
    domain: record.domain,
    policy_id: record.policyId,
    policy_version: record.policyVersion,
    budget_class: record.budgetClass,
    route: record.route,
    max_reasoning_tokens: record.reasoningTokensAllocated,
    estimated_cost_usd: record.estimatedCostUsd,
  };

  const outcome = {
    record_type: "outcome",
    request_id: record.requestId,
    reasoning_tokens_used: record.reasoningTokensUsed,
    reasoning_tokens_allocated: record.reasoningTokensAllocated,
    output_tokens: record.outputTokens,
    stop_reason: record.stopReason,
    escalation_count: record.escalationCount,
    verification_result: record.verificationResult,
    guardrail_input_result: record.guardrailInputResult,
    guardrail_output_result: record.guardrailOutputResult,
    confidence_level: record.confidenceLevel,
    actual_cost_usd: record.estimatedCostUsd,
    e2e_latency_ms: record.latencyMs,
  };

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div>
        <h4 className="section-label mb-2">Decision Record</h4>
        <pre className="overflow-x-auto rounded-lg bg-muted/40 border border-border/30 p-4 text-[11px] leading-relaxed font-mono-tight text-foreground/80">
          {JSON.stringify(decision, null, 2)}
        </pre>
      </div>
      <div>
        <h4 className="section-label mb-2">Outcome Record</h4>
        <pre className="overflow-x-auto rounded-lg bg-muted/40 border border-border/30 p-4 text-[11px] leading-relaxed font-mono-tight text-foreground/80">
          {JSON.stringify(outcome, null, 2)}
        </pre>
      </div>
    </div>
  );
}

export default function AuditPage() {
  const [budgetFilter, setBudgetFilter] = useState<"all" | BudgetClass>("all");
  const [verificationFilter, setVerificationFilter] = useState<"all" | VerificationResult>("all");
  const [stopReasonFilter, setStopReasonFilter] = useState<"all" | StopReason>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  const filtered = useMemo(() => {
    return DEMO_AUDIT_RECORDS.filter((rec) => {
      if (budgetFilter !== "all" && rec.budgetClass !== budgetFilter) return false;
      if (verificationFilter !== "all" && rec.verificationResult !== verificationFilter) return false;
      if (stopReasonFilter !== "all" && rec.stopReason !== stopReasonFilter) return false;
      if (searchQuery && !rec.requestId.toLowerCase().includes(searchQuery.toLowerCase()))
        return false;
      return true;
    });
  }, [budgetFilter, verificationFilter, stopReasonFilter, searchQuery]);

  const selectClass =
    "rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-[#3730A3]/30";

  return (
    <div className="space-y-5">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={budgetFilter}
          onChange={(e) => setBudgetFilter(e.target.value as "all" | BudgetClass)}
          className={selectClass}
          aria-label="Filter by budget class"
        >
          <option value="all">All Budget Classes</option>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
          <option value="critical">critical</option>
        </select>

        <select
          value={verificationFilter}
          onChange={(e) => setVerificationFilter(e.target.value as "all" | VerificationResult)}
          className={selectClass}
          aria-label="Filter by verification result"
        >
          <option value="all">All Verification</option>
          <option value="correct">correct</option>
          <option value="incorrect">incorrect</option>
          <option value="unverifiable">unverifiable</option>
          <option value="none">none</option>
          <option value="skipped">skipped</option>
        </select>

        <select
          value={stopReasonFilter}
          onChange={(e) => setStopReasonFilter(e.target.value as "all" | StopReason)}
          className={selectClass}
          aria-label="Filter by stop reason"
        >
          <option value="all">All Stop Reasons</option>
          <option value="natural_boundary">natural_boundary</option>
          <option value="budget_exhausted">budget_exhausted</option>
          <option value="cache_hit">cache_hit</option>
          <option value="fast_path_default">fast_path_default</option>
        </select>

        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search request ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search by request ID"
            className="rounded-md border border-border bg-card py-1.5 pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-[#3730A3]/30"
          />
        </div>

        <Badge variant="secondary" className="ml-auto font-mono-tight text-[10px]">
          {filtered.length} of {DEMO_AUDIT_RECORDS.length} records
        </Badge>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border/50">
              <th className="w-6 px-2 py-2.5" />
              <th className="px-3 py-2.5 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Time</th>
              <th className="px-3 py-2.5 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Request ID</th>
              <th className="hidden md:table-cell px-3 py-2.5 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Tenant</th>
              <th className="px-3 py-2.5 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Budget</th>
              <th className="hidden md:table-cell px-3 py-2.5 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Route</th>
              <th className="hidden md:table-cell px-3 py-2.5 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Stop Reason</th>
              <th className="px-3 py-2.5 text-right text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Tokens</th>
              <th className="px-3 py-2.5 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Verification</th>
              <th className="hidden md:table-cell px-3 py-2.5 text-right text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Cost</th>
              <th className="hidden md:table-cell px-3 py-2.5 text-right text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Latency</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((rec) => {
              const isExpanded = expandedRow === rec.requestId;
              return (
                <Fragment key={rec.requestId}>
                  <tr
                    className={`border-b border-border/30 cursor-pointer transition-colors hover:bg-muted/20 ${
                      isExpanded ? "bg-muted/15" : ""
                    }`}
                    onClick={() =>
                      setExpandedRow(isExpanded ? null : rec.requestId)
                    }
                    tabIndex={0}
                    role="button"
                    aria-expanded={isExpanded}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setExpandedRow(isExpanded ? null : rec.requestId);
                      }
                    }}
                  >
                    <td className="px-2 py-2 text-muted-foreground">
                      {isExpanded ? (
                        <ChevronDown className="h-3 w-3" />
                      ) : (
                        <ChevronRight className="h-3 w-3" />
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono-tight text-muted-foreground whitespace-nowrap">
                      {new Date(rec.timestamp).toLocaleTimeString()}
                    </td>
                    <td className="px-3 py-2 font-mono-tight max-w-[100px] truncate">{rec.requestId}</td>
                    <td className="hidden md:table-cell px-3 py-2 text-muted-foreground">{rec.tenantId}</td>
                    <td className="px-3 py-2">
                      <BudgetBadge budgetClass={rec.budgetClass} />
                    </td>
                    <td className="hidden md:table-cell px-3 py-2 font-mono-tight text-muted-foreground">
                      {rec.route}
                    </td>
                    <td className="hidden md:table-cell px-3 py-2 font-mono-tight text-muted-foreground">
                      {rec.stopReason}
                    </td>
                    <td className="px-3 py-2 text-right font-mono-tight">
                      {rec.reasoningTokensUsed}/{rec.reasoningTokensAllocated}
                    </td>
                    <td className="px-3 py-2">
                      <Badge
                        variant={
                          rec.verificationResult === "correct"
                            ? "default"
                            : rec.verificationResult === "incorrect"
                              ? "destructive"
                              : "secondary"
                        }
                        className="text-[10px]"
                      >
                        {rec.verificationResult}
                      </Badge>
                    </td>
                    <td className="hidden md:table-cell px-3 py-2 text-right font-mono-tight">
                      ${rec.estimatedCostUsd.toFixed(4)}
                    </td>
                    <td className="hidden md:table-cell px-3 py-2 text-right font-mono-tight">
                      {rec.latencyMs}ms
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="border-b border-border/30">
                      <td colSpan={11} className="px-6 py-5 bg-muted/10">
                        <DetailPanel record={rec} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
