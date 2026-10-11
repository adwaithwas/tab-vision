import type { ButtonHTMLAttributes, ReactNode } from "react";
import { LoaderCircle } from "lucide-react";

export type ButtonVariant = "primary" | "secondary" | "outline" | "ghost";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  isBusy?: boolean;
  busyLabel?: string;
  children: ReactNode;
}

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  outline: "btn-outline",
  ghost: "btn-ghost",
};

/**
 * Button matching the DESIGN.md recipes exactly: IBM Plex Mono 13px/600 label,
 * 11px 22px padding, 3px radius, restrained 180ms transitions.
 */
export function Button({
  variant = "primary",
  isBusy = false,
  busyLabel,
  children,
  className,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={["btn", VARIANT_CLASS[variant], className].filter(Boolean).join(" ")}
      disabled={disabled || isBusy}
      aria-busy={isBusy || undefined}
      {...rest}
    >
      {isBusy && (
        <LoaderCircle aria-hidden="true" size={14} strokeWidth={2} className="spin shrink-0" />
      )}
      <span>{isBusy && busyLabel ? busyLabel : children}</span>
    </button>
  );
}