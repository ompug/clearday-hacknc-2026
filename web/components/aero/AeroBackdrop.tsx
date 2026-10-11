/** Decorative Frutiger Aero backdrop: floating glass bubbles and a light streak over the sky/grass body. */
const BUBBLES = [
  { left: "6%", top: "18%", size: "5rem", delay: "0s" },
  { left: "18%", top: "64%", size: "2.5rem", delay: "-4s" },
  { left: "42%", top: "10%", size: "1.75rem", delay: "-7s" },
  { left: "74%", top: "40%", size: "6.5rem", delay: "-2s" },
  { left: "88%", top: "72%", size: "3rem", delay: "-9s" },
  { left: "58%", top: "78%", size: "2rem", delay: "-5s" },
  { left: "30%", top: "36%", size: "1.25rem", delay: "-11s" },
];

export function AeroBackdrop() {
  return (
    <div aria-hidden="true" className="aero-backdrop">
      <div className="aero-backdrop-streak" />
      {BUBBLES.map((b, i) => (
        <span
          key={i}
          className="aero-backdrop-bubble"
          style={{
            left: b.left,
            top: b.top,
            width: b.size,
            height: b.size,
            animationDelay: b.delay,
          }}
        />
      ))}
    </div>
  );
}
