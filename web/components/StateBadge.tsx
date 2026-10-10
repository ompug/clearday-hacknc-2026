import { STATE_LABELS, type BubbleState } from "@/lib/bubbles";
import { CheckIcon, CloudSunIcon, FlagIcon, StormIcon, SunIcon } from "./icons";

const ICONS: Record<BubbleState, (props: { className?: string }) => React.ReactNode> = {
  clear: SunIcon,
  watch: CloudSunIcon,
  tight: StormIcon,
  waiting: CheckIcon,
  disputed: FlagIcon,
};

// Text colours are AA on white glass: navy 13:1, alert red 5.9:1.
const TONE: Record<BubbleState, string> = {
  clear: "text-navy-900",
  watch: "text-navy-800",
  tight: "text-alert-700",
  waiting: "text-navy-900",
  disputed: "text-navy-800",
};

export function StateIcon({ state, className }: { state: BubbleState; className?: string }) {
  const Icon = ICONS[state];
  return <Icon className={className} />;
}

/** Icon plus text label for a bubble state. Never colour alone. */
export function StateBadge({
  state,
  extra,
  className = "",
  hidden = false,
  small = false,
}: {
  state: BubbleState;
  /** Optional prefix such as "Due in 3 days". */
  extra?: string;
  className?: string;
  /** Hide from assistive tech when the same text is already in a button's name. */
  hidden?: boolean;
  small?: boolean;
}) {
  return (
    <span
      aria-hidden={hidden || undefined}
      className={`inline-flex items-center gap-1.5 rounded-full bg-white/95 px-2.5 py-0.5 font-semibold ${small ? "text-xs" : "text-sm"} shadow-sm ring-1 ring-navy-900/10 ${TONE[state]} ${className}`}
    >
      <StateIcon state={state} className="size-4 shrink-0" />
      <span>
        {extra ? `${extra} · ` : ""}
        {STATE_LABELS[state]}
      </span>
    </span>
  );
}
