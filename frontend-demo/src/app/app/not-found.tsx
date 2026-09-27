import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";

export default function AppNotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-4">
      <div className="w-full max-w-md text-center">
        <p className="section-label mb-2">Route Not Found</p>
        <p className="font-mono-tight text-sm text-muted-foreground mb-1">404</p>
        <p className="text-sm text-muted-foreground mt-4 mb-8">
          The requested control surface does not exist.
        </p>
        <Link href="/app" className={buttonVariants({ size: "sm" })}>
          Return to Overview
        </Link>
      </div>
    </div>
  );
}
