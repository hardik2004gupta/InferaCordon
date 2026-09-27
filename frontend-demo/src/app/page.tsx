"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Shield, BookOpen, TrendingDown, Cpu, ArrowRight } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { InferenceVisual } from "@/components/landing/InferenceVisual";
import { PillarCard } from "@/components/landing/PillarCard";

const sectionReveal = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0 },
};

export default function LandingPage() {
  return (
    <div className="min-h-dvh">
      {/* ── Nav ── */}
      <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary">
              <Cpu className="h-4 w-4 text-primary-foreground" />
            </div>
            <span className="text-sm font-semibold tracking-tight">InferaCordon</span>
          </div>
          <nav className="hidden items-center gap-6 text-sm text-muted-foreground md:flex">
            <a href="#problem" className="transition-colors hover:text-foreground">Problem</a>
            <a href="#pillars" className="transition-colors hover:text-foreground">Pillars</a>
            <a href="#routing" className="transition-colors hover:text-foreground">Routing</a>
          </nav>
          <Link href="/app" className={buttonVariants({ size: "sm" })}>
            Open Console
            <ArrowRight className="ml-1 h-3.5 w-3.5" />
          </Link>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="mx-auto max-w-6xl px-4 pb-12 pt-20 md:pt-32">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="mb-6"
        >
          <Badge variant="secondary" className="mb-6 text-xs font-normal">
            Interactive Demo
          </Badge>
          <h1 className="mb-2 text-5xl font-bold uppercase tracking-[0.12em] text-foreground md:text-6xl lg:text-7xl">
            INFERACORDON
          </h1>
          <p className="mb-4 text-2xl font-medium leading-tight tracking-tight text-foreground md:text-3xl">
            Govern Reasoning Compute.
          </p>
          <p className="mb-8 max-w-xl text-base leading-relaxed text-muted-foreground md:text-lg">
            A control plane that makes reasoning tokens schedulable, policy-bounded,
            cost-attributed, and quality-guaranteed — sitting between your application
            and model infrastructure.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/app" className={buttonVariants({ size: "lg" })}>
              Explore Control Plane
              <ArrowRight className="ml-1.5 h-4 w-4" />
            </Link>
            <Link href="/app/playground" className={buttonVariants({ variant: "outline", size: "lg" })}>
              View Interactive Demo
            </Link>
          </div>
        </motion.div>

        {/* Pipeline visualization */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.5 }}
          className="mt-16 rounded-xl border border-border bg-card p-5 shadow-[var(--shadow-card)]"
        >
          <div className="mb-1 flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-emerald-500" />
            <span className="font-mono-tight text-[11px] text-muted-foreground">
              Simulated inference pipeline
            </span>
          </div>
          <InferenceVisual />
        </motion.div>
      </section>

      {/* ── Problem ── */}
      <section id="problem" className="border-t border-border surface-inset">
        <div className="mx-auto max-w-6xl px-4 py-24 md:py-32">
          <motion.div
            variants={sectionReveal}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5 }}
          >
            <p className="section-label mb-3">The Problem</p>
            <h2 className="mb-12 max-w-2xl text-3xl font-semibold tracking-tight md:text-4xl">
              Reasoning tokens are invisible, uncontrolled compute.
            </h2>
          </motion.div>

          <div className="grid gap-8 md:grid-cols-3">
            {/* Overthinking */}
            <motion.div
              variants={sectionReveal}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true }}
              transition={{ delay: 0, duration: 0.45 }}
              className="rounded-lg border border-border bg-card p-6"
            >
              <h3 className="mb-3 text-base font-semibold text-foreground">Overthinking</h3>
              <p className="mb-4 text-sm leading-relaxed text-muted-foreground">
                1,800 thinking tokens on a query requiring 200. No mechanism to
                recognize this and stop earlier.
              </p>
              {/* Visual: token bar showing waste */}
              <div className="space-y-1">
                <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
                  <div className="h-full w-[11%] rounded-l-full bg-indigo-500" />
                  <div className="h-full w-[89%] rounded-r-full bg-rose-300" />
                </div>
                <div className="flex justify-between font-mono-tight text-[10px] text-muted-foreground">
                  <span>200 needed</span>
                  <span className="text-rose-500">1,600 wasted</span>
                </div>
              </div>
            </motion.div>

            {/* Underthinking */}
            <motion.div
              variants={sectionReveal}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true }}
              transition={{ delay: 0.1, duration: 0.45 }}
              className="rounded-lg border border-border bg-card p-6"
            >
              <h3 className="mb-3 text-base font-semibold text-foreground">Underthinking</h3>
              <p className="mb-4 text-sm leading-relaxed text-muted-foreground">
                Conservative global ceiling produces a shallow answer on a
                complex query. No error is raised.
              </p>
              {/* Visual: truncated bar */}
              <div className="space-y-1">
                <div className="relative flex h-3 w-full overflow-hidden rounded-full bg-muted">
                  <div className="h-full w-[30%] rounded-l-full bg-indigo-500" />
                  <div className="absolute right-[70%] top-0 h-full w-0.5 bg-rose-500" />
                </div>
                <div className="flex justify-between font-mono-tight text-[10px] text-muted-foreground">
                  <span className="text-rose-500">cut off at 256</span>
                  <span>needed 1,024</span>
                </div>
              </div>
            </motion.div>

            {/* Budget Blindness */}
            <motion.div
              variants={sectionReveal}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true }}
              transition={{ delay: 0.2, duration: 0.45 }}
              className="rounded-lg border border-border bg-card p-6"
            >
              <h3 className="mb-3 text-base font-semibold text-foreground">Budget Blindness</h3>
              <p className="mb-4 text-sm leading-relaxed text-muted-foreground">
                No per-request allocation. No tenant-level cost attribution. No
                SLO-aware routing. No audit trail.
              </p>
              {/* Visual: blind metrics */}
              <div className="flex gap-3">
                {["cost", "route", "audit"].map((label) => (
                  <div
                    key={label}
                    className="flex flex-col items-center rounded-md border border-dashed border-border px-3 py-2"
                  >
                    <span className="font-mono-tight text-lg text-muted-foreground/30">?</span>
                    <span className="font-mono-tight text-[9px] text-muted-foreground/50">{label}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ── Four Pillars ── */}
      <section id="pillars" className="border-t border-border">
        <div className="mx-auto max-w-6xl px-4 py-24 md:py-32">
          <motion.div
            variants={sectionReveal}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5 }}
          >
            <p className="section-label mb-3">Four Pillars</p>
            <h2 className="mb-12 max-w-2xl text-3xl font-semibold tracking-tight md:text-4xl">
              Reasoning compute as a managed resource.
            </h2>
          </motion.div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <PillarCard
              index={0}
              icon={<Shield className="h-4 w-4" />}
              title="Guardrails"
              description="PII redaction, injection detection, and safety classification at both input and output boundaries."
              detail="Presidio · DeBERTa ONNX · Llama Guard"
            />
            <PillarCard
              index={1}
              icon={<BookOpen className="h-4 w-4" />}
              title="Governance"
              description="Versioned YAML policies with immutable audit trail. Every decision recorded with its governing policy version."
              detail="Append-only JSONL · Per-request attribution"
            />
            <PillarCard
              index={2}
              icon={<TrendingDown className="h-4 w-4" />}
              title="Cost Optimization"
              description="Semantic cache, budget-class routing, and verification-triggered escalation. Cost per correct answer as primary metric."
              detail="FAISS · all-MiniLM-L6-v2 · Semantic cache"
            />
            <PillarCard
              index={3}
              icon={<Cpu className="h-4 w-4" />}
              title="Inference Optimization"
              description="Native vLLM LogitProcessor enforcing per-request reasoning token budgets at the delimiter boundary."
              detail="BudgetLogitProcessor · </think> detection"
            />
          </div>
        </div>
      </section>

      {/* ── Budget Model ── */}
      <section id="routing" className="border-t border-border surface-inset">
        <div className="mx-auto max-w-6xl px-4 py-24 md:py-32">
          <motion.div
            variants={sectionReveal}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5 }}
          >
            <p className="section-label mb-3">Reasoning Budget Model</p>
            <h2 className="mb-12 max-w-2xl text-3xl font-semibold tracking-tight md:text-4xl">
              Four budget classes. Two models. One GPU.
            </h2>
          </motion.div>

          <motion.div
            variants={sectionReveal}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            transition={{ delay: 0.1, duration: 0.45 }}
            className="overflow-x-auto rounded-lg border border-border bg-card shadow-[var(--shadow-card)]"
          >
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-5 py-3.5 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Class</th>
                  <th className="px-5 py-3.5 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Model</th>
                  <th className="px-5 py-3.5 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">Reasoning</th>
                  <th className="px-5 py-3.5 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">Output</th>
                  <th className="px-5 py-3.5 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Verification</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { cls: "low", pill: "bg-emerald-100 text-emerald-800", model: "Qwen2.5-3B-Instruct", reasoning: "0", output: "256", verify: "none" },
                  { cls: "medium", pill: "bg-indigo-100 text-indigo-800", model: "DeepSeek-R1-7B-Q4", reasoning: "512", output: "512", verify: "verifiable_only" },
                  { cls: "high", pill: "bg-amber-100 text-amber-800", model: "DeepSeek-R1-7B-Q4", reasoning: "1,024", output: "1,024", verify: "required" },
                  { cls: "critical", pill: "bg-rose-100 text-rose-800", model: "DeepSeek-R1-7B-Q4", reasoning: "2,048", output: "1,024", verify: "required" },
                ].map((row) => (
                  <tr key={row.cls} className="border-b border-border last:border-0 transition-colors hover:bg-muted/30">
                    <td className="px-5 py-4">
                      <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${row.pill}`}>
                        {row.cls}
                      </span>
                    </td>
                    <td className="px-5 py-4 font-mono-tight text-xs">{row.model}</td>
                    <td className="px-5 py-4 text-right font-mono-tight text-xs">{row.reasoning}</td>
                    <td className="px-5 py-4 text-right font-mono-tight text-xs">{row.output}</td>
                    <td className="px-5 py-4 font-mono-tight text-xs text-muted-foreground">{row.verify}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </motion.div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-6xl px-4 py-24 md:py-32">
          <motion.div
            variants={sectionReveal}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="flex flex-col items-start"
          >
            <h2 className="mb-6 text-3xl font-semibold tracking-tight md:text-4xl">
              Explore the control plane.
            </h2>
            <Link
              href="/app"
              className="group inline-flex items-center gap-3 text-lg font-medium text-primary transition-colors hover:text-primary/80"
            >
              Open Console
              <ArrowRight className="h-5 w-5 transition-transform group-hover:translate-x-1" />
            </Link>
          </motion.div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-6 text-xs text-muted-foreground">
          <span>InferaCordon</span>
          <span className="font-mono-tight">Interactive demo · Simulated telemetry</span>
        </div>
      </footer>
    </div>
  );
}
