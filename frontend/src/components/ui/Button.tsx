import { type ReactNode, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  children: ReactNode;
}

const variantClasses: Record<Variant, string> = {
  primary: "bg-accent text-white border border-accent hover:brightness-95",
  secondary: "bg-surface text-ink border border-line hover:bg-accent-bg/40",
  ghost: "bg-transparent text-ink2 border border-transparent hover:bg-surface",
};

const sizeClasses: Record<Size, string> = {
  sm: "text-[12.5px] px-3.5 py-2",
  md: "text-[13.5px] px-4.5 py-2.5",
};

export function Button({
  variant = "primary",
  size = "md",
  icon,
  children,
  className = "",
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center gap-1.5 rounded-pill font-bold font-body
        whitespace-nowrap transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      {...rest}
    >
      {icon}
      <span>{children}</span>
    </button>
  );
}
