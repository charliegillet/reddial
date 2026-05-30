import { motion, useSpring, useTransform, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

interface AnimatedCounterProps {
  value: number;
  suffix?: string;
}

export function AnimatedCounter({ value, suffix = "" }: AnimatedCounterProps) {
  // Guard against undefined/null/NaN/Infinity so we never animate toward (or
  // render) a non-finite value.
  const safeValue = Number.isFinite(value) ? value : 0;
  const reduce = useReducedMotion();

  const spring = useSpring(safeValue, { mass: 1, stiffness: 75, damping: 20 });
  const display = useTransform(spring, (current) =>
    (Number.isFinite(current) ? Math.round(current) : 0) + suffix
  );

  // Static fallback that is ALWAYS the real number. If the spring never ticks
  // (backgrounded tab / reduced-motion / paused rAF), we still render the
  // correct value instead of a frozen 0.
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    spring.set(safeValue);
  }, [safeValue, spring]);

  useEffect(() => {
    // Only opt into the live (motion-value-driven) text once mounted and when
    // motion is allowed. Until then we render the plain, correct number.
    if (!reduce) setAnimate(true);
  }, [reduce]);

  if (!animate) {
    return <span>{Math.round(safeValue) + suffix}</span>;
  }

  return <motion.span>{display}</motion.span>;
}
