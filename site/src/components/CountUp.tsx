import { useEffect, useState } from "react";
import { useInView } from "../lib/useInView";

interface CountUpProps {
  value: number;
  decimals?: number;
  suffix?: string;
  duration?: number;
}

/** Counts up once when scrolled into view; jumps straight to the value for reduced motion. */
export function CountUp({ value, decimals = 0, suffix = "", duration = 1100 }: CountUpProps) {
  const [ref, inView] = useInView<HTMLSpanElement>({ threshold: 0.4 });
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (!inView) {
      return;
    }

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDisplay(value);
      return;
    }

    let frame = 0;
    const started = performance.now();

    function tick(now: number) {
      const progress = Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(value * eased);
      if (progress < 1) {
        frame = window.requestAnimationFrame(tick);
      }
    }

    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [inView, value, duration]);

  return (
    <span ref={ref}>
      {display.toFixed(decimals)}
      {suffix}
    </span>
  );
}
