import { type HTMLAttributes, type ReactNode } from "react";

export function Card({
  children,
  className = "",
  ...rest
}: HTMLAttributes<HTMLDivElement> & { children: ReactNode }) {
  return (
    <div
      className={`bg-surface2 border border-line rounded-card shadow-[0_2px_0_var(--color-line)] ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
