import { motion, useSpring, useTransform } from "framer-motion";
import { useEffect } from "react";

interface AnimatedCounterProps {
  value: number;
  suffix?: string;
}

export function AnimatedCounter({ value, suffix = "" }: AnimatedCounterProps) {
  const spring = useSpring(0, { mass: 1, stiffness: 75, damping: 20 });
  const display = useTransform(spring, (current) => Math.round(current) + suffix);

  useEffect(() => {
    spring.set(value);
  }, [value, spring]);

  return <motion.span>{display}</motion.span>;
}
