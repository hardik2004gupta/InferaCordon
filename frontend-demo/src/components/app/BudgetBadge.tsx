import { cn } from "@/lib/utils";
import type { BudgetClass } from "@/demo/types";

const styles: Record<BudgetClass, { bg: string; text: string; dot: string }> = {
  low: { bg: "bg-emerald-50", text: "text-[#047857]", dot: "bg-[#047857]" },
  medium: { bg: "bg-indigo-50", text: "text-[#3730A3]", dot: "bg-[#3730A3]" },
  high: { bg: "bg-amber-50", text: "text-[#B45309]", dot: "bg-[#B45309]" },
  critical: { bg: "bg-rose-50", text: "text-[#BE123C]", dot: "bg-[#BE123C]" },
};

export function BudgetBadge({ budgetClass, className }: { budgetClass: BudgetClass; className?: string }) {
  const s = styles[budgetClass];
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
      s.bg, s.text, className
    )}>
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
      {budgetClass}
    </span>
  );
}
