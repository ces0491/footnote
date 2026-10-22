import { cn } from "@/lib/utils";

/** The double dagger, the mark a footnote is called with: every card here points to its sources. */
export function FootnoteMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 12 20" aria-hidden className={className} fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round">
      <path d="M6 1.6v16.8M1.8 6.4h8.4M1.8 13.6h8.4" />
    </svg>
  );
}

/** "Footnote" with its mark set where a footnote's would be. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-start font-semibold tracking-tight font-stretch-85%", className)}>
      Footnote
      <FootnoteMark className="mt-[0.12em] ml-[0.08em] h-[0.62em] w-auto text-cite" />
    </span>
  );
}
