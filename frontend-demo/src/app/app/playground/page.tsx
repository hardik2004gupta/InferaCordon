"use client";

import { useState, useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Send, Zap, ChevronDown, ChevronRight, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { BudgetBadge } from "@/components/app/BudgetBadge";
import { PipelineStages } from "@/components/playground/PipelineStages";
import type { PipelineGroup, StageStatus } from "@/components/playground/PipelineStages";
import { TraceWaterfall } from "@/components/playground/TraceWaterfall";
import { DEMO_SCENARIOS } from "@/demo/demoData";
import { getTraceForScenario } from "@/demo/demoTraces";
import { useSimulation } from "@/demo/simulation";
import type { SimulationStep } from "@/demo/simulation";
import type { DemoScenario } from "@/demo/types";

/* ─── Constants ─── */

const GROUP_LABELS: Record<string, string> = {
  REQUEST: "Auth",
  UNDERSTAND: "Analyze",
  ALLOCATE: "Allocate",
  PROTECT: "Guard",
  INFER: "Infer",
  VERIFY: "Verify",
  RESPOND: "Respond",
};

const GROUP_ORDER = [
  "REQUEST",
  "UNDERSTAND",
  "ALLOCATE",
  "PROTECT",
  "INFER",
  "VERIFY",
  "RESPOND",
];

/* ─── Helpers ─── */

function deriveGroupStatus(steps: SimulationStep[], group: string): StageStatus {
  const groupSteps = steps.filter((s) => s.group === group && s.status !== "skipped");
  if (groupSteps.length === 0) return "pending";
  if (groupSteps.some((s) => s.status === "error")) return "error";
  if (groupSteps.some((s) => s.status === "running")) return "running";
  if (groupSteps.some((s) => s.status === "warning")) return "warning";
  if (groupSteps.every((s) => s.status === "completed")) return "completed";
  return "pending";
}

/* ─── Complexity Bar ─── */

function ComplexityBar({ score }: { score: number }) {
  const pct = (score / 10) * 100;
  const color =
    score <= 3.5
      ? "var(--color-emerald)"
      : score <= 6.5
      ? "var(--color-indigo)"
      : score <= 8.5
      ? "var(--color-amber)"
      : "var(--color-rose)";

  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-muted-foreground">Complexity</span>
      <div className="relative h-1 w-16 overflow-hidden rounded-full bg-border">
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="font-mono-tight text-[10px]" style={{ color }}>
        {score.toFixed(1)}
      </span>
    </div>
  );
}

/* ─── Inline metric ─── */

function MetricValue({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-baseline gap-1 text-[11px]">
      <span className="font-mono-tight text-foreground/80">{value}</span>
      <span className="text-muted-foreground/50 text-[10px]">{label}</span>
    </span>
  );
}

/* ─── Metadata row ─── */

function MetadataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-0.5">
      <span className="text-muted-foreground text-[11px]">{label}</span>
      <span className="font-mono-tight text-[11px] text-right">{value}</span>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   Page
   ═══════════════════════════════════════════════════════════════════ */

export default function PlaygroundPage() {
  const [selected, setSelected] = useState<DemoScenario>(DEMO_SCENARIOS[1]);
  const [rawTraceOpen, setRawTraceOpen] = useState(false);
  const simulation = useSimulation();

  const isRunning = simulation.status === "running";
  const isFinished = simulation.status === "completed" || simulation.status === "blocked";

  const spans = useMemo(() => getTraceForScenario(selected.id), [selected.id]);

  const pipelineGroups: PipelineGroup[] = useMemo(() => {
    if (simulation.steps.length === 0) {
      return GROUP_ORDER.map((g) => ({
        label: GROUP_LABELS[g],
        status: "pending" as StageStatus,
      }));
    }
    return GROUP_ORDER.map((g) => ({
      label: GROUP_LABELS[g],
      status: deriveGroupStatus(simulation.steps, g),
    }));
  }, [simulation.steps]);

  function handleRun() {
    setRawTraceOpen(false);
    simulation.run(selected.id);
  }

  function handleReset() {
    simulation.reset();
    setRawTraceOpen(false);
  }

  function handleSelectScenario(scenario: DemoScenario) {
    setSelected(scenario);
    simulation.reset();
    setRawTraceOpen(false);
  }

  const activeScenario = simulation.scenario ?? selected;

  return (
    <div className="space-y-5">
      {/* ── Demo notice ── */}
      <div className="flex items-center gap-2 rounded border border-[var(--color-amber)]/20 bg-[var(--color-amber)]/[0.04] px-3 py-1.5 text-[11px] text-[var(--color-amber)]">
        <Zap className="h-3 w-3 shrink-0" />
        Simulated inference - select a scenario and run to see the full pipeline in action
      </div>

      {/* ── Scenario selector ── */}
      <div className="flex flex-wrap gap-1.5">
        {DEMO_SCENARIOS.map((s) => (
          <button
            key={s.id}
            onClick={() => handleSelectScenario(s)}
            disabled={isRunning}
            className={`rounded-full border px-3 py-1 text-[11px] transition-all duration-150 disabled:opacity-40 ${
              selected.id === s.id
                ? "border-[var(--color-indigo)] bg-[var(--color-indigo)]/[0.06] font-medium text-[var(--color-indigo)]"
                : "border-transparent bg-muted/60 text-muted-foreground hover:bg-muted"
            }`}
          >
            {s.name}
          </button>
        ))}
      </div>

      {/* ── Main split layout ── */}
      <div className="grid gap-5 lg:grid-cols-[3fr_2fr]">
        {/* ═══ LEFT: Prompt + Pipeline + Response ═══ */}
        <div className="space-y-4">
          {/* Prompt editor card */}
          <div className="rounded-lg border border-border surface-paper p-4">
            <div className="section-label mb-2">Prompt</div>
            <div className="surface-technical rounded-md border border-border p-3">
              <textarea
                readOnly
                value={selected.prompt}
                rows={3}
                className="w-full resize-none bg-transparent font-mono-tight text-[13px] leading-relaxed text-foreground/90 focus:outline-none"
              />
            </div>
            <div className="mt-2.5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="font-mono-tight text-[10px] text-muted-foreground/60">
                  ~{Math.ceil(selected.prompt.length / 4)} tokens
                </span>
                <ComplexityBar score={selected.complexityScore} />
              </div>
              <div className="flex items-center gap-2">
                {isFinished && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleReset}
                    className="h-7 text-[11px]"
                  >
                    <RotateCcw className="mr-1 h-3 w-3" />
                    Reset
                  </Button>
                )}
                <Button
                  size="sm"
                  onClick={handleRun}
                  disabled={isRunning}
                  className="h-7 text-[11px]"
                >
                  <Send className="mr-1 h-3 w-3" />
                  {isRunning ? "Running…" : "Run"}
                </Button>
              </div>
            </div>
          </div>

          {/* Pipeline stages */}
          {(isRunning || isFinished) && (
            <div className="rounded-lg border border-border surface-paper px-4 py-1">
              <PipelineStages groups={pipelineGroups} />
              {isRunning && (
                <div className="pb-1.5 text-center font-mono-tight text-[10px] text-muted-foreground/50">
                  {simulation.elapsedMs}ms
                </div>
              )}
            </div>
          )}

          {/* Response */}
          <AnimatePresence mode="wait">
            {isFinished && (
              <motion.div
                key={activeScenario.id + "-resp"}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                className="rounded-lg border border-border surface-paper p-4"
              >
                <div className="section-label mb-2">Response</div>
                <div className="rounded-md border border-border bg-[var(--surface-inset)] px-3 py-2.5 text-[13px] leading-relaxed whitespace-pre-wrap">
                  {activeScenario.response}
                </div>

                {/* Metrics strip */}
                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border pt-3">
                  <BudgetBadge budgetClass={activeScenario.budgetClass} />
                  <MetricValue
                    label="reasoning"
                    value={`${activeScenario.reasoningTokensUsed}/${activeScenario.reasoningTokensAllocated}`}
                  />
                  <MetricValue label="stop" value={activeScenario.stopReason} />
                  <MetricValue
                    label="verification"
                    value={activeScenario.verificationResult}
                  />
                  {activeScenario.escalationCount > 0 && (
                    <Badge
                      variant="secondary"
                      className="font-mono-tight text-[10px] px-1.5 py-0"
                    >
                      escalation: {activeScenario.escalationCount}
                    </Badge>
                  )}
                  <MetricValue
                    label="cost"
                    value={`$${activeScenario.estimatedCostUsd.toFixed(4)}`}
                  />
                  <MetricValue label="latency" value={`${activeScenario.latencyMs}ms`} />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* ═══ RIGHT: Trace + Metadata + Raw ═══ */}
        <div className="space-y-4">
          {/* Trace waterfall */}
          <div className="rounded-lg border border-border surface-paper p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="section-label">Trace Waterfall</span>
              <span className="font-mono-tight text-[9px] text-muted-foreground/50">
                simulated
              </span>
            </div>
            <TraceWaterfall spans={spans} />
          </div>

          {/* Request metadata */}
          <div className="rounded-lg border border-border surface-paper p-4">
            <div className="section-label mb-2">Request Metadata</div>
            <div>
              <MetadataRow label="Model" value={selected.model} />
              <MetadataRow
                label="Complexity"
                value={selected.complexityScore.toFixed(1)}
              />
              <MetadataRow
                label="Policy"
                value={`${selected.policyId} v${selected.policyVersion}`}
              />
              <MetadataRow label="Input guardrail" value={selected.guardrailInputResult} />
              <MetadataRow label="Confidence" value={selected.confidenceLevel} />
            </div>
          </div>

          {/* Collapsible raw trace */}
          <div className="rounded-lg border border-border surface-paper">
            <button
              type="button"
              onClick={() => setRawTraceOpen((v) => !v)}
              className="flex w-full items-center gap-1.5 px-4 py-2.5 text-[11px] font-medium transition-colors hover:bg-muted/30"
            >
              {rawTraceOpen ? (
                <ChevronDown className="h-3 w-3 text-muted-foreground/50" />
              ) : (
                <ChevronRight className="h-3 w-3 text-muted-foreground/50" />
              )}
              Raw Trace
            </button>
            <AnimatePresence initial={false}>
              {rawTraceOpen && (
                <motion.div
                  key="raw-trace"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <pre className="max-h-72 overflow-auto border-t border-border px-4 py-3 font-mono-tight text-[10px] leading-relaxed text-muted-foreground">
                    {JSON.stringify(selected, null, 2)}
                  </pre>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}
