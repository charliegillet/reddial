import { motion } from "framer-motion";
import { type AutoImproveCurve } from "../api";

interface ImprovementCurveProps {
  curve: AutoImproveCurve;
}

// Inline-SVG line chart of breach_rate per round. The Y axis is INVERTED so a
// DESCENDING breach rate reads as a line sloping visually downward = improving.
//
// CRITICAL (per the locked design): visibility is NEVER gated on opacity. The
// polyline + circle marks are drawn at full opacity; framer-motion only animates
// the polyline `pathLength` as a draw-on flourish. If the tween freezes (slow
// device / backgrounded tab / reduced-motion), the chart still shows fully.
export function ImprovementCurve({ curve }: ImprovementCurveProps) {
  const rounds = curve?.rounds ?? [];
  const rates = curve?.breach_rate ?? [];
  const n = Math.min(rounds.length, rates.length);

  // Degenerate guard: a line needs >= 2 points.
  if (n < 2) {
    return (
      <div className="improvement-curve">
        <div className="view-empty" style={{ padding: "32px 24px" }}>
          <p>Need at least two rounds to plot an improvement curve.</p>
        </div>
        <p className="curve-caption">breach rate vs OUR attack suite, per round</p>
      </div>
    );
  }

  // Viewbox geometry (unitless; scales to container width via CSS).
  const W = 640;
  const H = 220;
  const padL = 44;
  const padR = 20;
  const padT = 20;
  const padB = 36;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  // Y domain: 0 .. max(breach_rate, baseline) clamped to >= a small floor so a
  // converged-to-zero run still has a visible axis. Y is inverted in the mapping.
  const maxRate = Math.max(...rates.slice(0, n), 0.0001);
  const x = (i: number) => padL + (n === 1 ? 0 : (i / (n - 1)) * plotW);
  // Inverted: rate 0 -> bottom (y = padT + plotH), rate max -> top (y = padT).
  const y = (r: number) => padT + (1 - r / maxRate) * plotH;

  const points = Array.from({ length: n }, (_, i) => [x(i), y(rates[i])]);
  const polyPoints = points.map(([px, py]) => `${px},${py}`).join(" ");

  // Baseline gridline = round 0 (the WEAK starting breach rate).
  const baselineY = y(rates[0]);

  return (
    <div className="improvement-curve">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label="Breach rate per round, descending = improving"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Axes */}
        <line
          x1={padL}
          y1={padT}
          x2={padL}
          y2={padT + plotH}
          stroke="var(--glass-border)"
          strokeWidth={1}
        />
        <line
          x1={padL}
          y1={padT + plotH}
          x2={padL + plotW}
          y2={padT + plotH}
          stroke="var(--glass-border)"
          strokeWidth={1}
        />

        {/* Baseline gridline (starting breach rate) */}
        <line
          x1={padL}
          y1={baselineY}
          x2={padL + plotW}
          y2={baselineY}
          stroke="var(--status-danger)"
          strokeWidth={1}
          strokeDasharray="4 4"
          opacity={0.5}
        />
        <text
          x={padL + 4}
          y={baselineY - 6}
          fill="var(--text-faint)"
          fontSize={10}
          fontFamily="var(--font-mono)"
        >
          baseline {Math.round(rates[0] * 100)}%
        </text>

        {/* The improving line — full opacity; only pathLength is animated. */}
        <motion.polyline
          points={polyPoints}
          fill="none"
          stroke="var(--accent-acid)"
          strokeWidth={2.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.9, ease: "easeOut" }}
          style={{ filter: "drop-shadow(0 0 6px var(--accent-acid-dim))" }}
        />

        {/* Round marks + labels */}
        {points.map(([px, py], i) => (
          <g key={i}>
            <circle
              cx={px}
              cy={py}
              r={4}
              fill="var(--bg-color)"
              stroke="var(--accent-acid)"
              strokeWidth={2}
            />
            <text
              x={px}
              y={padT + plotH + 18}
              fill="var(--text-faint)"
              fontSize={10}
              fontFamily="var(--font-mono)"
              textAnchor="middle"
            >
              R{rounds[i]}
            </text>
          </g>
        ))}
      </svg>
      <p className="curve-caption">breach rate vs OUR attack suite, per round</p>
    </div>
  );
}
