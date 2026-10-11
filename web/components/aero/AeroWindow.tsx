import { useId, type ReactNode } from "react";

/**
 * Win7-style glass window: a sky-glass frame with a title bar and a white content
 * pane. The frame is the Gestalt common region for everything inside it. The
 * window controls are decorative only (hidden from assistive tech).
 */
export function AeroWindow({
  title,
  icon,
  actions,
  children,
  as: Tag = "section",
  headingLevel = 2,
  className = "",
  bodyClassName = "p-5 sm:p-6",
  controls = true,
}: {
  title: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  as?: "section" | "div" | "article" | "aside";
  headingLevel?: 1 | 2 | 3;
  className?: string;
  bodyClassName?: string;
  controls?: boolean;
}) {
  const id = useId();
  const H = `h${headingLevel}` as "h1" | "h2" | "h3";
  return (
    <Tag aria-labelledby={id} className={`aero-window ${className}`}>
      <div className="aero-titlebar">
        {icon ? (
          <span aria-hidden="true" className="grid size-6 shrink-0 place-items-center">
            {icon}
          </span>
        ) : null}
        <H
          id={id}
          className={`font-semibold ${headingLevel === 1 ? "text-xl sm:text-2xl" : "text-lg"}`}
        >
          {title}
        </H>
        {actions ? <div className="ml-auto flex items-center gap-2">{actions}</div> : null}
        {controls && !actions ? (
          <span aria-hidden="true" className="aero-titlebar-controls">
            <span />
            <span />
            <span />
          </span>
        ) : null}
      </div>
      <div className={`aero-window-body ${bodyClassName}`}>{children}</div>
    </Tag>
  );
}
