import { type ReactNode } from "react";

type Tone = "accent" | "success" | "warn" | "neutral";

const toneClasses: Record<Tone, string> = {
  accent: "bg-accent-bg text-accent-ink",
  success: "bg-success-bg text-success",
  warn: "bg-warn-bg text-warn",
  neutral: "bg-surface text-ink2 border border-line",
};

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-1 rounded-pill text-[11px]
        font-bold font-body tracking-wide uppercase ${toneClasses[tone]}`}
    >
      {children}
    </span>
  );
}
