"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Terminal,
  BarChart3,
  FileText,
  ScrollText,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navGroups = [
  {
    label: "Control",
    items: [
      { href: "/app", label: "Overview", icon: LayoutDashboard },
      { href: "/app/playground", label: "Playground", icon: Terminal },
    ],
  },
  {
    label: "Observe",
    items: [
      { href: "/app/observability", label: "Observability", icon: BarChart3 },
      { href: "/app/health", label: "System Health", icon: Activity },
    ],
  },
  {
    label: "Govern",
    items: [
      { href: "/app/policies", label: "Policies", icon: FileText },
      { href: "/app/audit", label: "Audit Log", icon: ScrollText },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden lg:flex h-dvh w-[220px] shrink-0 flex-col border-r border-border bg-[var(--surface-canvas)]">
      {/* Wordmark */}
      <div className="flex h-14 items-center gap-2.5 px-5">
        <div className="flex h-6 w-6 items-center justify-center rounded bg-primary">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="text-primary-foreground">
            <path d="M2 3h8M2 6h5M2 9h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        </div>
        <span className="text-[13px] font-semibold tracking-tight text-foreground">InferaCordon</span>
      </div>

      {/* Nav groups */}
      <nav aria-label="Main navigation" className="flex-1 overflow-y-auto px-3 pt-2">
        {navGroups.map((group) => (
          <div key={group.label} className="mb-4">
            <div className="mb-1 px-2 text-[10px] font-medium uppercase tracking-[0.1em] text-muted-foreground/50">
              {group.label}
            </div>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const isActive =
                  item.href === "/app"
                    ? pathname === "/app"
                    : pathname.startsWith(item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={isActive ? "page" : undefined}
                      className={cn(
                        "relative flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13px] transition-all",
                        isActive
                          ? "bg-primary/[0.06] font-medium text-primary"
                          : "text-muted-foreground hover:bg-accent hover:text-foreground"
                      )}
                    >
                      {isActive && (
                        <div className="absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-r-full bg-primary" />
                      )}
                      <item.icon className="h-[15px] w-[15px] shrink-0" aria-hidden="true" />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-border px-5 py-3">
        <div className="flex items-center gap-2">
          <div className="h-[6px] w-[6px] rounded-full bg-amber-500" />
          <span className="text-[10px] font-medium text-muted-foreground">Demo</span>
        </div>
        <p className="mt-0.5 text-[9px] tracking-wide text-muted-foreground/40">
          Simulated telemetry
        </p>
      </div>
    </aside>
  );
}
