"use client";

import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { Button } from "@/components/ui/button";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 surface-canvas">
      <div className="w-full max-w-md text-center">
        <p className="section-label mb-2">System Error</p>
        <p className="font-mono-tight text-sm text-muted-foreground mb-1">500</p>
        <p className="text-sm text-muted-foreground mt-4 mb-8">
          An unexpected error occurred in the control plane interface.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Button variant="outline" size="sm" onClick={() => reset()}>
            Try Again
          </Button>
          <Link href="/app" className={buttonVariants({ size: "sm" })}>
            Return to Overview
          </Link>
        </div>
      </div>
    </div>
  );
}
