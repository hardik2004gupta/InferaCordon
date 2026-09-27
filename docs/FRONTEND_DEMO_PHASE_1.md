# Frontend Demo — Phase 1 Report

## 1. Design Direction

Premium light theme inspired by Linear/Vercel/Stripe aesthetic. Warm off-white background (`oklch(0.988 0.002 90)`) with deep indigo primary (`oklch(0.372 0.148 276)`). Typography pairs Inter (UI text) with Geist Mono (all metric values, token counts, costs, latency readings). Spatial system uses 8px grid with subtle borders and minimal shadows. No dark mode in Phase 1 — light-only for visual consistency.

Semantic status colors: emerald (healthy/pass), amber (warning/degraded), rose (error/blocked), blue (medium budget class). All defined as CSS custom properties on `:root`.

## 2. Architecture

Next.js 16 App Router with TypeScript. Two route groups:
- `/` — Landing page (marketing, product story, four pillars)
- `/app/*` — App shell with persistent sidebar navigation

All pages are statically generated. No server-side data fetching. No API routes. No middleware. The entire application can be deployed as a static site on Vercel.

## 3. Component System

Three component layers:

**UI primitives** (`components/ui/`): shadcn/ui v4 components — Button, Badge, Skeleton. Generated via `npx shadcn@latest add`. Use Base UI (Radix successor) under the hood.

**App components** (`components/app/`): Sidebar (pathname-aware navigation), AppHeader (dynamic title), MetricCard (label + monospace value + trend), BudgetBadge (semantic-colored budget class pill).

**Landing components** (`components/landing/`): InferenceVisual (animated pipeline diagram with Framer Motion), PillarCard (viewport-triggered entrance animation).

## 4. Route Structure

| Route | Page | Status |
|-------|------|--------|
| `/` | Landing page | Complete |
| `/app` | Dashboard overview | Complete |
| `/app/playground` | Inference playground | Complete |
| `/app/observability` | Observability dashboard | Phase 2 placeholder |
| `/app/policies` | Policy viewer | Complete |
| `/app/audit` | Audit log explorer | Complete |
| `/app/health` | System health | Complete |

## 5. Demo Data Architecture

Self-contained data layer in `src/demo/` with 8 files:

- `types.ts` — Full TypeScript type system covering BudgetClass, StopReason, VerificationResult, GuardrailResult, CircuitBreakerState, DemoScenario, DemoMetrics, DemoAuditRecord, DemoPolicy, TraceSpan, ServiceHealth
- `demoData.ts` — 6 scenarios covering all key system behaviors
- `demoMetrics.ts` — Aggregate metrics + time series arrays
- `demoPolicies.ts` — 2 policies matching CLAUDE.md YAML schema
- `demoAudit.ts` — 8 audit records with full governance fields
- `demoHealth.ts` — 5 service health entries
- `demoTraces.ts` — Per-scenario trace waterfall spans
- `index.ts` — Barrel export

All values are deterministic (no `Math.random()`). All values are plausible and internally consistent with the documented architecture.

## 6. Simulated Scenario Architecture

Six scenarios demonstrate the full range of InferaCordon behaviors:

1. **Simple Query** — low budget, Qwen cheap model, 0 reasoning tokens
2. **Complex Reasoning** — high budget, DeepSeek, 687/1024 tokens used, natural stop
3. **Budget Exhaustion** — high budget, 1024/1024, forced delimiter (budget_exhausted)
4. **Escalation** — medium→high retry after verification failure, escalation_count: 1
5. **Guardrail Block** — injection detected, request blocked before inference
6. **Circuit Breaker** — GPU pressure reroutes to cheap model

Each scenario includes: prompt, response, budget class, model, token counts, stop reason, verification result, cost estimate, latency, and trace spans.

## 7. Responsive Strategy

Tailwind CSS breakpoints (sm/md/lg). Sidebar collapses on mobile via responsive classes. Grid layouts adapt from 1→2→3→4 columns. Tables use `overflow-x-auto` for horizontal scroll on narrow viewports. Landing page hero stacks vertically on mobile.

## 8. Motion System

Framer Motion for two categories:
- **Landing page entrance animations** — Staggered pipeline steps in InferenceVisual, viewport-triggered PillarCard entrances with `whileInView`
- **Interactive state transitions** — Scenario selection in Playground (future Phase 2: animated trace waterfall, metric transitions)

All animations use `ease-out` timing, 150ms for UI transitions, 300-500ms for entrance animations.

## 9. Vercel Strategy

Zero-config Vercel deployment:
- Framework auto-detected as Next.js
- Root directory: `frontend-demo`
- No environment variables required
- No build-time API calls
- All pages statically generated at build time
- Output: standard Next.js static build

## 10. Separation from Production Code

Strict isolation:
- `frontend-demo/` is a completely independent Next.js project
- No imports from `frontend/`, `gateway/`, `policy_engine/`, or any other production directory
- No shared `node_modules`, no shared configuration
- No requests to localhost:8000, 8001, 8002, 9090, or 3000
- Demo data is self-contained in `src/demo/`
- The existing production codebase was not modified (except `.claude/launch.json` for dev server configuration)

## 11. Phase 2 Implementation Plan

- **Observability Dashboard** — Five-tab panel (Cost, Quality, Reliability, Performance, Governance) with Recharts time-series charts, gauge visualizations, and live-updating metric cards
- **Enhanced Playground** — Animated trace waterfall with real-time span rendering, scenario comparison mode, raw JSON trace viewer
- **Audit Log Filtering** — Client-side filtering by tenant, budget class, stop reason, date range, request ID search
- **Policy Diff View** — Side-by-side version comparison with additions/removals highlighted
- **Failure Injection Panel** — 10 buttons for demo-mode failure scenarios (visible only in demo mode)
- **Mobile-first responsive polish** — Full sidebar drawer, touch-optimized interactions
- **Production API integration** — Replace demo data layer with real FastAPI gateway clients
