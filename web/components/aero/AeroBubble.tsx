import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { BubbleState } from "@/lib/bubbles";

/**
 * Glass bubble as a real <button>. Callers pass an accessible name via children
 * text or `aria-label`, and must show the state as icon plus text inside.
 */
export function AeroBubble({
  state = "clear",
  fill,
  size = "8rem",
  children,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  state?: BubbleState;
  /** 0..1 paid fraction, drawn as a liquid fill. */
  fill?: number;
  size?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      data-state={state}
      className={`bubble grid place-items-center p-3 text-center ${className}`}
      style={{ width: size, height: size }}
      {...rest}
    >
      {fill !== undefined ? (
        <span
          aria-hidden="true"
          className="bubble-fill"
          style={{ height: `${Math.round(Math.max(0, Math.min(1, fill)) * 100)}%` }}
        />
      ) : null}
      <span className="bubble-content">{children}</span>
    </button>
  );
}
