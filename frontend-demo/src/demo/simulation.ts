"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import type { DemoScenario } from "./types";
import { getScenarioById } from "./demoData";

export interface SimulationStep {
  id: string;
  name: string;
  group: "REQUEST" | "UNDERSTAND" | "ALLOCATE" | "PROTECT" | "INFER" | "VERIFY" | "RESPOND";
  status: "pending" | "running" | "completed" | "error" | "warning" | "skipped";
  durationMs: number;
  metadata?: Record<string, string | number>;
}

export interface SimulationState {
  status: "idle" | "running" | "completed" | "blocked";
  steps: SimulationStep[];
  currentStepIndex: number;
  scenario: DemoScenario | null;
  elapsedMs: number;
  run: (scenarioId: string) => void;
  reset: () => void;
}

interface StepTemplate {
  id: string;
  name: string;
  group: SimulationStep["group"];
}

const PIPELINE_STEPS: StepTemplate[] = [
  { id: "auth", name: "Authentication", group: "REQUEST" },
  { id: "complexity", name: "Complexity Scoring", group: "UNDERSTAND" },
  { id: "policy", name: "Policy Lookup", group: "UNDERSTAND" },
  { id: "budget", name: "Budget Allocation", group: "ALLOCATE" },
  { id: "guardrail", name: "Guardrail Check", group: "PROTECT" },
  { id: "cache", name: "Cache Lookup", group: "ALLOCATE" },
  { id: "inference", name: "Inference", group: "INFER" },
  { id: "verification", name: "Verification", group: "VERIFY" },
  { id: "escalation", name: "Escalation", group: "VERIFY" },
  { id: "response", name: "Response", group: "RESPOND" },
  { id: "audit", name: "Audit Event", group: "RESPOND" },
];

// Deterministic timing per scenario and step
function getStepDuration(scenarioId: string, stepId: string): number {
  const timings: Record<string, Record<string, number>> = {
    "scenario-simple": {
      auth: 1, complexity: 2, policy: 1, budget: 1, guardrail: 45,
      cache: 4, inference: 240, verification: 0, escalation: 0,
      response: 8, audit: 2,
    },
    "scenario-complex": {
      auth: 1, complexity: 3, policy: 1, budget: 1, guardrail: 82,
      cache: 5, inference: 2400, verification: 34, escalation: 0,
      response: 12, audit: 3,
    },
    "scenario-budget-exhausted": {
      auth: 1, complexity: 3, policy: 1, budget: 1, guardrail: 78,
      cache: 5, inference: 3800, verification: 0, escalation: 0,
      response: 14, audit: 3,
    },
    "scenario-escalation": {
      auth: 1, complexity: 2, policy: 1, budget: 1, guardrail: 68,
      cache: 4, inference: 1200, verification: 28, escalation: 1800,
      response: 10, audit: 3,
    },
    "scenario-guardrail": {
      auth: 1, complexity: 2, policy: 1, budget: 1, guardrail: 42,
      cache: 0, inference: 0, verification: 0, escalation: 0,
      response: 4, audit: 2,
    },
    "scenario-circuit-breaker": {
      auth: 1, complexity: 2, policy: 1, budget: 1, guardrail: 52,
      cache: 4, inference: 420, verification: 0, escalation: 0,
      response: 8, audit: 2,
    },
  };
  return timings[scenarioId]?.[stepId] ?? 10;
}

function getStepMetadata(scenario: DemoScenario, stepId: string): Record<string, string | number> | undefined {
  switch (stepId) {
    case "auth":
      return { tenant: scenario.policyId.includes("enterprise") ? "acme_corp" : "demo_tenant" };
    case "complexity":
      return { score: scenario.complexityScore };
    case "policy":
      return { policyId: scenario.policyId, version: scenario.policyVersion };
    case "budget":
      return { class: scenario.budgetClass, model: scenario.model, maxTokens: scenario.reasoningTokensAllocated };
    case "guardrail":
      return { result: scenario.guardrailInputResult, direction: "input" };
    case "cache":
      return { hit: scenario.cacheHit ? 1 : 0 };
    case "inference":
      return { model: scenario.model, tokensUsed: scenario.reasoningTokensUsed, stopReason: scenario.stopReason };
    case "verification":
      return { result: scenario.verificationResult, type: scenario.verificationResult === "none" ? "none" : "gsm8k" };
    case "escalation":
      return { from: "medium", to: "high", attempt: 1 };
    case "response":
      return { outputTokens: scenario.outputTokens, confidence: scenario.confidenceLevel };
    case "audit":
      return { recordType: "decision+outcome" };
    default:
      return undefined;
  }
}

function resolveStepOutcome(scenario: DemoScenario, stepId: string): SimulationStep["status"] {
  if (stepId === "guardrail" && scenario.guardrailInputResult === "block") return "error";
  if (stepId === "guardrail" && scenario.guardrailInputResult === "flag") return "warning";
  if (stepId === "verification" && scenario.escalationCount > 0 && scenario.verificationResult === "correct") return "warning";
  if (stepId === "inference" && scenario.stopReason === "budget_exhausted") return "warning";
  return "completed";
}

function shouldSkipStep(scenario: DemoScenario, stepId: string): boolean {
  // Guardrail block: skip everything after guardrail except response and audit
  if (scenario.guardrailInputResult === "block") {
    if (["cache", "inference", "verification", "escalation"].includes(stepId)) return true;
  }
  // No escalation unless escalationCount > 0
  if (stepId === "escalation" && scenario.escalationCount === 0) return true;
  // No verification for "none" or "skipped"
  if (stepId === "verification" && (scenario.verificationResult === "none" || scenario.verificationResult === "skipped")) return true;
  // No cache step when not a hit and guardrail blocked
  if (stepId === "cache" && scenario.guardrailInputResult === "block") return true;
  return false;
}

function shouldStopAfter(scenario: DemoScenario, stepId: string): boolean {
  return stepId === "guardrail" && scenario.guardrailInputResult === "block";
}

function buildInitialSteps(scenario: DemoScenario): SimulationStep[] {
  return PIPELINE_STEPS.map((t) => ({
    id: t.id,
    name: t.name,
    group: t.group,
    status: shouldSkipStep(scenario, t.id) ? "skipped" as const : "pending" as const,
    durationMs: getStepDuration(scenario.id, t.id),
    metadata: getStepMetadata(scenario, t.id),
  }));
}

export function useSimulation(): SimulationState {
  const [status, setStatus] = useState<SimulationState["status"]>("idle");
  const [steps, setSteps] = useState<SimulationStep[]>([]);
  const [currentStepIndex, setCurrentStepIndex] = useState(-1);
  const [scenario, setScenario] = useState<DemoScenario | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const startTimeRef = useRef(0);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => () => { mountedRef.current = false; }, []);

  const cleanup = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    cleanup();
    setStatus("idle");
    setSteps([]);
    setCurrentStepIndex(-1);
    setScenario(null);
    setElapsedMs(0);
  }, [cleanup]);

  const run = useCallback((scenarioId: string) => {
    cleanup();

    const sc = getScenarioById(scenarioId);
    if (!sc || !mountedRef.current) return;

    const initialSteps = buildInitialSteps(sc);
    setScenario(sc);
    setSteps(initialSteps);
    setStatus("running");
    setCurrentStepIndex(-1);
    setElapsedMs(0);

    startTimeRef.current = Date.now();
    elapsedTimerRef.current = setInterval(() => {
      setElapsedMs(Date.now() - startTimeRef.current);
    }, 50);

    // Schedule step transitions
    let cumulativeDelay = 0;
    const runnableSteps = initialSteps
      .map((s, i) => ({ step: s, index: i }))
      .filter(({ step }) => step.status !== "skipped");

    runnableSteps.forEach(({ step, index }, seqIdx) => {
      const startDelay = cumulativeDelay;
      // Transition speed multiplier for visual pacing (real durations are too fast for some steps)
      const visualDuration = Math.max(step.durationMs, 80);
      const endDelay = startDelay + visualDuration;

      // Mark step as running
      timersRef.current.push(setTimeout(() => {
        if (!mountedRef.current) return;
        setCurrentStepIndex(index);
        setSteps((prev) => prev.map((s, i) => i === index ? { ...s, status: "running" } : s));
      }, startDelay));

      // Mark step as completed/error/warning
      timersRef.current.push(setTimeout(() => {
        if (!mountedRef.current) return;
        const outcome = resolveStepOutcome(sc, step.id);
        setSteps((prev) => prev.map((s, i) => i === index ? { ...s, status: outcome } : s));

        // If this is the last step or we should stop
        const isLast = seqIdx === runnableSteps.length - 1;
        const shouldStop = shouldStopAfter(sc, step.id);

        if (shouldStop) {
          // Mark remaining non-skipped steps after guardrail block as skipped for response/audit
          // Actually response and audit still run after a block
          setStatus("blocked");
          if (elapsedTimerRef.current) {
            clearInterval(elapsedTimerRef.current);
            elapsedTimerRef.current = null;
          }
          setElapsedMs(Date.now() - startTimeRef.current);
        }
        if (isLast && !shouldStop) {
          setStatus("completed");
          if (elapsedTimerRef.current) {
            clearInterval(elapsedTimerRef.current);
            elapsedTimerRef.current = null;
          }
          setElapsedMs(Date.now() - startTimeRef.current);
        }
      }, endDelay));

      cumulativeDelay = endDelay + 30; // 30ms gap between steps
    });
  }, [cleanup]);

  useEffect(() => () => { cleanup(); }, [cleanup]);

  return {
    status,
    steps,
    currentStepIndex,
    scenario,
    elapsedMs,
    run,
    reset,
  };
}
