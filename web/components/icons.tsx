/** Original line icons. Decorative by default: pair each with visible text. */
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { title?: string };

function Svg({ title, children, ...props }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      focusable="false"
      {...props}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

export function SunIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </Svg>
  );
}

export function CloudSunIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 3v1.5M5.6 5.6l1 1M3 12h1.5M18.4 5.6l-1 1" />
      <path d="M8.5 11a3.5 3.5 0 0 1 6.8-1" />
      <path d="M17 20H8a4 4 0 1 1 .9-7.9A5 5 0 0 1 18.5 13 3.5 3.5 0 0 1 17 20Z" />
    </Svg>
  );
}

export function StormIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M17.5 15A4.5 4.5 0 0 0 16 6.3 6 6 0 0 0 4.5 9 3.5 3.5 0 0 0 6 15.8" />
      <path d="m13 12-3 5h4l-3 5" />
    </Svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12.5 2.7 2.7L16 9.8" />
    </Svg>
  );
}

export function FlagIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 21V4M5 4h11l-2 4 2 4H5" />
    </Svg>
  );
}

export function PeopleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3 20a6 6 0 0 1 12 0" />
      <path d="M16 4.5a3 3 0 0 1 0 6M18 14.5a6 6 0 0 1 3 5.5" />
    </Svg>
  );
}

export function StackIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 13 9 5 9-5" />
    </Svg>
  );
}

export function ListIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9 6h11M9 12h11M9 18h11" />
      <circle cx="4.5" cy="6" r="1" />
      <circle cx="4.5" cy="12" r="1" />
      <circle cx="4.5" cy="18" r="1" />
    </Svg>
  );
}

export function BubblesIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="14" r="5" />
      <circle cx="17" cy="7" r="3.5" />
      <circle cx="18" cy="17" r="2.2" />
    </Svg>
  );
}

export function SettingsIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="10" cy="17" r="2" />
    </Svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 6l12 12M18 6 6 18" />
    </Svg>
  );
}

/** Original Clearday mark: a sun rising inside a bubble. */
export function ClearMark(props: IconProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      width="1em"
      height="1em"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <defs>
        <radialGradient id="cm-glass" cx="35%" cy="30%" r="75%">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="0.55" stopColor="#9ad8f7" />
          <stop offset="1" stopColor="#2d8fd0" />
        </radialGradient>
      </defs>
      <circle cx="16" cy="16" r="14.5" fill="url(#cm-glass)" stroke="#ffffff" strokeOpacity="0.8" />
      <path d="M8 21a8 8 0 0 1 16 0Z" fill="#ffffff" fillOpacity="0.9" />
      <ellipse cx="11" cy="9" rx="5" ry="2.6" fill="#ffffff" fillOpacity="0.75" />
    </svg>
  );
}
