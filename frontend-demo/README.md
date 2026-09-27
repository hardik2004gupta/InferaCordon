# InferaCordon - Frontend Demo

Interactive portfolio demo for the InferaCordon governed AI inference control plane. Runs standalone with zero backend dependencies - all telemetry is simulated.

## Quick Start

```bash
cd frontend-demo
npm install
npm run dev        # http://localhost:3001
```

Deploy to Vercel:

```bash
npx vercel
```

## What This Is

A Next.js application that demonstrates InferaCordon's four pillars - Guardrails, Governance, Cost Optimization, and Inference Optimization - through an interactive UI with deterministic demo scenarios, animated pipeline simulations, and rich data visualization. Every metric, trace, chart, and audit record is generated from a self-contained demo data layer.

This is **not** the production frontend. It shares no code with the existing `frontend/` directory and makes no requests to the InferaCordon backend.

## Pages

| Page | Route | Features |
|------|-------|----------|
| **Landing** | `/` | Product story, four pillars, pipeline visual, budget model table |
| **Dashboard** | `/app` | Compute economics, routing mix bar, circuit breaker status, cost sparkline, recent activity |
| **Playground** | `/app/playground` | 6 scenarios, animated pipeline simulation, trace waterfall, complexity score, raw JSON view |
| **Observability** | `/app/observability` | 5-tab dashboard (Cost/Quality/Reliability/Performance/Governance) with Recharts |
| **Policies** | `/app/policies` | Split-view policy manager with expandable sections and YAML view |
| **Audit Log** | `/app/audit` | Filterable table with search, expandable decision/outcome JSON records |
| **System Health** | `/app/health` | Service cards, circuit breakers, failure injection panel (8 scenarios), event timeline |

## Architecture

```
frontend-demo/
├── src/
│   ├── app/              # Next.js App Router pages
│   │   ├── page.tsx      # Landing page
│   │   └── app/          # App shell with sidebar
│   │       ├── page.tsx           # Dashboard overview
│   │       ├── playground/        # Inference playground with simulation engine
│   │       ├── observability/     # 5-tab observability dashboard
│   │       ├── policies/          # Split-view policy manager
│   │       ├── audit/             # Filterable audit log explorer
│   │       └── health/            # System health + failure injection
│   ├── components/
│   │   ├── ui/           # shadcn/ui primitives
│   │   ├── app/          # App shell components (Sidebar, Header, MetricCard, BudgetBadge)
│   │   ├── landing/      # Landing page components
│   │   └── playground/   # PipelineStages, TraceWaterfall
│   └── demo/             # Demo data layer
│       ├── types.ts              # TypeScript types for all domain concepts
│       ├── demoData.ts           # 6 deterministic inference scenarios
│       ├── demoMetrics.ts        # Aggregate metrics and time series
│       ├── demoPolicies.ts       # 2 YAML-equivalent policy documents
│       ├── demoAudit.ts          # 10 governance audit records
│       ├── demoHealth.ts         # 5 service health entries
│       ├── demoTraces.ts         # Per-scenario trace span arrays
│       ├── simulation.ts         # useSimulation hook (pipeline animation engine)
│       ├── observabilityData.ts  # Quality, Performance, Reliability, Governance, Cost data
│       ├── failureScenarios.ts   # 8 failure injection scenarios
│       └── index.ts              # Barrel export
```

## How Simulated Values Are Labeled

- Amber banner at the top of every app page: "Simulated telemetry" / "Simulated audit records"
- Sidebar bottom indicator: "Demo Environment · Simulated telemetry"
- Header badge: "Demo"
- Footer on landing page: "Simulated environment · Not production telemetry"
- No value is ever presented as a measured production result

## Vercel Deployment

Standard Next.js App Router with static generation. All pages prerendered at build time.

1. Push `frontend-demo/` to a repository
2. Import in Vercel, set root directory to `frontend-demo`
3. Framework preset: Next.js (auto-detected)
4. No environment variables required

## Production Build

```bash
npm run build    # Static generation, no backend required
npm start        # Serve production build locally
```

No environment variables, GPU, Docker, or backend service required.

## Design System

| Token | Value | Usage |
|-------|-------|-------|
| Canvas | `#F8F8F6` | Page background |
| Paper | `#FFFFFF` | Card/surface background |
| Primary | `#3730A3` | Deep indigo accent |
| Emerald | `#047857` | Healthy, pass, low budget |
| Amber | `#B45309` | Warning, degraded, high budget |
| Rose | `#BE123C` | Error, blocked, critical |
| Sans | Inter | All UI text |
| Mono | Geist Mono | Metrics, IDs, technical values |

Surface hierarchy: Canvas → Paper → Raised → Inset → Dense → Technical.

## Demo Scenarios

| Scenario | Demonstrates |
|----------|-------------|
| Simple Query | Low complexity → cheap model routing, 0 reasoning tokens |
| Complex Analysis | High complexity → reasoning model, verification pass |
| Budget Exhaustion | LogitProcessor forces `</think>` at budget ceiling |
| Verification Failure → Escalation | Failed verification triggers retry at higher budget |
| Guardrail Block | Injection detection blocks request, pipeline short-circuits |
| Circuit Breaker | GPU pressure triggers routing downgrade |

## Known Limitations

- All data is deterministic and simulated - no live inference occurs
- Charts display static demo datasets, not streaming telemetry
- Failure injection simulates system behavior, not actual service failures
- The semantic cache, admission control, and rate limiter are conceptual demonstrations
- No authentication or multi-tenant switching in the demo

## Tech Stack

- **Framework:** Next.js 16 (App Router, TypeScript)
- **UI:** shadcn/ui v4 (Base UI primitives, Tailwind CSS 4)
- **Charts:** Recharts 3
- **Animation:** Framer Motion
- **Icons:** Lucide React
- **Fonts:** Inter (sans), Geist Mono (monospace)
- **Theme:** Custom premium light theme with surface hierarchy
