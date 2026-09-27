"use client";

import { useState } from "react";
import { DEMO_SERVICES } from "@/demo/demoHealth";
import { DEMO_METRICS } from "@/demo/demoMetrics";
import { FAILURE_SCENARIOS, type FailureScenario } from "@/demo/failureScenarios";
import { DEMO_RELIABILITY_DATA } from "@/demo/observabilityData";

const statusDot = {
  operational: "bg-[#047857]",
  degraded: "bg-[#B45309]",
  down: "bg-[#BE123C]",
};

const severityStyle = {
  critical: "bg-rose-100 text-rose-800",
  warning: "bg-amber-100 text-amber-800",
  info: "bg-slate-100 text-slate-700",
};

const stepDotColor: Record<string, string> = {
  trigger: "bg-[#BE123C]",
  detect: "bg-[#B45309]",
  respond: "bg-[#3730A3]",
  outcome: "bg-[#047857]",
  audit: "bg-slate-400",
};

const eventDotColor: Record<string, string> = {
  incident: "bg-[#BE123C]",
  warning: "bg-[#B45309]",
  recovery: "bg-[#047857]",
  info: "bg-slate-400",
};

export default function HealthPage() {
  const [selectedFailure, setSelectedFailure] = useState<string | null>(null);

  return (
    <div className="space-y-8">
      {/* Circuit Breakers */}
      <div>
        <h2 className="section-label mb-4">System Signals</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {[
            {
              label: "GPU Pressure Circuit Breaker",
              state: DEMO_METRICS.gpuCbState,
              threshold: "KV-cache > 90% for 2 consecutive scrapes",
            },
            {
              label: "Latency Circuit Breaker",
              state: DEMO_METRICS.latencyCbState,
              threshold: "P99 TTFT > SLO for 3 consecutive windows",
            },
          ].map((cb) => (
            <div
              key={cb.label}
              className={`rounded-lg border border-border bg-card p-4 ${
                cb.state === "closed"
                  ? "border-l-4 border-l-[#047857]"
                  : "border-l-4 border-l-[#BE123C]"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium">{cb.label}</span>
              </div>
              <div className="mt-2.5 font-mono-tight text-lg font-semibold uppercase tracking-wider">
                {cb.state}
              </div>
              <p className="mt-1.5 font-mono-tight text-[10px] text-muted-foreground">
                {cb.threshold}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Service Cards */}
      <div>
        <h2 className="section-label mb-4">Services</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {DEMO_SERVICES.slice(0, 5).map((svc) => (
            <div
              key={svc.name}
              className="rounded-lg border border-border bg-card p-3.5"
            >
              <div className="flex items-center gap-2">
                <div className={`h-2 w-2 rounded-full ${statusDot[svc.status]}`} aria-hidden="true" />
                <span className="text-xs font-medium">{svc.name}</span>
                <span className="sr-only">Status: {svc.status}</span>
              </div>
              <div className="mt-3 space-y-1 text-[10px]">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Version</span>
                  <span className="font-mono-tight">{svc.version}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Req/s</span>
                  <span className="font-mono-tight">{svc.requestRate}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Errors</span>
                  <span className="font-mono-tight">{svc.errorRate}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">P95</span>
                  <span className="font-mono-tight">{svc.p95LatencyMs}ms</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Event Timeline */}
      <div>
        <h2 className="section-label mb-4">Event Timeline</h2>
        <div className="rounded-lg border border-border bg-card">
          <div className="divide-y divide-border/30">
            {DEMO_RELIABILITY_DATA.recentEvents.map((evt, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                <div className={`h-2 w-2 flex-shrink-0 rounded-full ${eventDotColor[evt.type]}`} aria-hidden="true" />
                <span className="font-mono-tight text-[10px] text-muted-foreground whitespace-nowrap">
                  {new Date(evt.timestamp).toLocaleTimeString()}
                </span>
                <span className="text-xs">{evt.event}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Failure Injection Panel */}
      <div>
        <h2 className="section-label mb-1">Failure Injection Panel</h2>
        <p className="mb-4 text-[10px] text-muted-foreground">
          DEMO_MODE=true -- select a scenario to inspect step-by-step system response
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {FAILURE_SCENARIOS.map((scenario) => {
            const isSelected = selectedFailure === scenario.id;
            return (
              <button
                key={scenario.id}
                onClick={() =>
                  setSelectedFailure(isSelected ? null : scenario.id)
                }
                className={`rounded-lg border bg-card p-3 text-left transition-colors ${
                  isSelected
                    ? "border-[#3730A3]/40 ring-1 ring-[#3730A3]/20"
                    : "border-border hover:bg-muted/20"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium">{scenario.name}</span>
                  <span
                    className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      severityStyle[scenario.severity]
                    }`}
                  >
                    {scenario.severity}
                  </span>
                </div>
                <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
                  {scenario.description}
                </p>
              </button>
            );
          })}
        </div>

        {/* Expanded failure detail */}
        {selectedFailure && (
          <FailureDetail
            scenario={FAILURE_SCENARIOS.find((s) => s.id === selectedFailure)!}
          />
        )}
      </div>
    </div>
  );
}

function FailureDetail({ scenario }: { scenario: FailureScenario }) {
  return (
    <div className="mt-4 rounded-lg border border-border bg-card p-5">
      <h3 className="text-xs font-semibold">{scenario.name}</h3>
      <p className="mt-1 text-[10px] text-muted-foreground">{scenario.description}</p>
      <div className="mt-4 space-y-0">
        {scenario.steps.map((step, i) => (
          <div key={i} className="flex items-start gap-3">
            <div className="flex flex-col items-center">
              <div className={`mt-0.5 h-2.5 w-2.5 rounded-full ${stepDotColor[step.status]}`} />
              {i < scenario.steps.length - 1 && (
                <div className="w-px flex-1 bg-border/50" style={{ minHeight: 24 }} />
              )}
            </div>
            <div className="pb-3">
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                {step.label}
              </span>
              <p className="text-xs">{step.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
