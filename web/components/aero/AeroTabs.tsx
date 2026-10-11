import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

/** Container for pill tabs. `light` for use on white glass (navy text), default for navy chrome. */
export function AeroTabs({
  label,
  light = false,
  className = "",
  children,
}: {
  label: string;
  light?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className={`aero-tabs ${light ? "aero-tabs-light" : ""} ${className}`}
    >
      {children}
    </div>
  );
}

/** Toggle-style pill tab (aria-pressed). */
export function AeroPillTab({
  active,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { active: boolean }) {
  return (
    <button type="button" aria-pressed={active} className={`aero-tab ${className}`} {...rest} />
  );
}

/** Navigation pill tab (aria-current="page" when active). */
export function AeroPillLink({
  href,
  active,
  children,
}: {
  href: string;
  active?: boolean;
  children: ReactNode;
}) {
  return (
    <Link href={href} aria-current={active ? "page" : undefined} className="aero-tab">
      {children}
    </Link>
  );
}
