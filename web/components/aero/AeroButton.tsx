import { forwardRef, type ButtonHTMLAttributes } from "react";

export type AeroButtonVariant = "primary" | "secondary" | "danger";

const VARIANT: Record<AeroButtonVariant, string> = {
  primary: "",
  secondary: "aero-btn-secondary",
  danger: "aero-btn-danger",
};

/** Glossy Aero gel button: highlight, inner glow, pressed state. Use `danger` sparingly. */
export const AeroButton = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: AeroButtonVariant; size?: "md" | "lg" }
>(function AeroButton({ variant = "primary", size = "md", className = "", type, ...rest }, ref) {
  const sizing = size === "lg" ? "min-h-12 px-7 text-lg" : "min-h-11 px-5";
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      className={`aero-btn ${VARIANT[variant]} ${sizing} ${className}`}
      {...rest}
    />
  );
});

/** Class string for links or other elements that should look like an Aero button. */
export function aeroButtonClass(variant: AeroButtonVariant = "primary", extra = "") {
  return `aero-btn ${VARIANT[variant]} min-h-11 px-5 ${extra}`;
}
