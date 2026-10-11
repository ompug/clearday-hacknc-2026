import type { ReactNode } from "react";

/** Small glossy pill. Pair with an icon and text; never colour alone. `alert` is the sparing red. */
export function AeroBadge({
  tone = "sky",
  icon,
  children,
  className = "",
}: {
  tone?: "sky" | "navy" | "alert";
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const t = tone === "navy" ? "aero-badge-navy" : tone === "alert" ? "aero-badge-alert" : "";
  return (
    <span className={`aero-badge ${t} ${className}`}>
      {icon ? (
        <span aria-hidden="true" className="inline-grid size-4 shrink-0 place-items-center">
          {icon}
        </span>
      ) : null}
      <span>{children}</span>
    </span>
  );
}
