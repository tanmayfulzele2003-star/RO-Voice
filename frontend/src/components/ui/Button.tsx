import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-primary text-primary-foreground hover:opacity-90 focus-visible:outline-primary",
  secondary:
    "bg-card text-foreground border border-border hover:bg-muted focus-visible:outline-primary",
  danger: "bg-danger text-danger-foreground hover:opacity-90 focus-visible:outline-danger",
  ghost: "text-foreground hover:bg-muted focus-visible:outline-primary",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 ${variantClasses[variant]} ${className}`}
      {...props}
    />
  );
}
