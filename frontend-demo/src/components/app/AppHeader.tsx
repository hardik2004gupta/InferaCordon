"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import {
  LayoutDashboard,
  Terminal,
  BarChart3,
  FileText,
  ScrollText,
  Activity,
  Menu,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";

const titleMap: Record<string, string> = {
  "/app": "Overview",
  "/app/playground": "Inference Playground",
  "/app/observability": "Observability",
  "/app/policies": "Policies",
  "/app/audit": "Audit Log",
  "/app/health": "System Health",
};

const mobileNav = [
  { href: "/app", label: "Overview", icon: LayoutDashboard },
  { href: "/app/playground", label: "Playground", icon: Terminal },
  { href: "/app/observability", label: "Observability", icon: BarChart3 },
  { href: "/app/health", label: "Health", icon: Activity },
  { href: "/app/policies", label: "Policies", icon: FileText },
  { href: "/app/audit", label: "Audit", icon: ScrollText },
];

export function AppHeader() {
  const pathname = usePathname();
  const title = titleMap[pathname] ?? "InferaCordon";
  const [mobileOpen, setMobileOpen] = useState(false);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

  useEffect(() => {
    if (!mobileOpen) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") closeMobile(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [mobileOpen, closeMobile]);

  return (
    <>
      <header className="flex h-12 items-center justify-between border-b border-border bg-[var(--surface-paper)] px-4 lg:px-6">
        <div className="flex items-center gap-3">
          {/* Mobile menu button */}
          <button
            type="button"
            className="lg:hidden -ml-1 p-1.5 text-muted-foreground hover:text-foreground"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu className="h-4 w-4" />
          </button>
          <h1 className="text-[13px] font-medium text-foreground">{title}</h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div className="h-[5px] w-[5px] rounded-full bg-emerald-500" />
            <span className="text-[11px] text-muted-foreground">Operational</span>
          </div>
          <span className="font-mono-tight text-[10px] text-muted-foreground/50">
            demo
          </span>
        </div>
      </header>

      {/* Mobile navigation sheet */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div
            className="absolute inset-0 bg-black/20 backdrop-blur-sm"
            aria-hidden="true"
            onClick={closeMobile}
          />
          <div className="absolute inset-y-0 left-0 w-64 bg-[var(--surface-paper)] shadow-xl">
            <div className="flex h-12 items-center justify-between border-b border-border px-4">
              <div className="flex items-center gap-2">
                <div className="flex h-5 w-5 items-center justify-center rounded bg-primary">
                  <svg width="10" height="10" viewBox="0 0 12 12" fill="none" className="text-primary-foreground">
                    <path d="M2 3h8M2 6h5M2 9h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                  </svg>
                </div>
                <span className="text-[13px] font-semibold tracking-tight">InferaCordon</span>
              </div>
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="p-1 text-muted-foreground"
                aria-label="Close navigation"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <nav className="p-3">
              <ul className="space-y-0.5">
                {mobileNav.map((item) => {
                  const isActive =
                    item.href === "/app"
                      ? pathname === "/app"
                      : pathname.startsWith(item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={() => setMobileOpen(false)}
                        className={cn(
                          "flex items-center gap-2.5 rounded-md px-3 py-2.5 text-[13px] transition-colors",
                          isActive
                            ? "bg-primary/[0.06] font-medium text-primary"
                            : "text-muted-foreground hover:bg-accent hover:text-foreground"
                        )}
                      >
                        <item.icon className="h-4 w-4 shrink-0" />
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </nav>
          </div>
        </div>
      )}
    </>
  );
}
