import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 surface-canvas">
      <div className="w-full max-w-md text-center">
        <p className="section-label mb-2">Route Not Found</p>
        <p className="font-mono-tight text-sm text-muted-foreground mb-1">404</p>
        <p className="text-sm text-muted-foreground mt-4 mb-8">
          The requested control surface does not exist.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Link href="/" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Landing
          </Link>
          <Link href="/app" className={buttonVariants({ size: "sm" })}>
            Open Console
          </Link>
        </div>
      </div>
    </div>
  );
}
