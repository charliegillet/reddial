import { ShieldCheck } from "lucide-react";
import { type Summary } from "../api";
import { motion } from "framer-motion";
import { AnimatedCounter } from "./AnimatedCounter";

interface ScorecardSummaryProps {
  summary: Summary;
  gradeColor: string;
}

export function ScorecardSummary({ summary, gradeColor }: ScorecardSummaryProps) {
  const grade = summary.max_grade ?? "—";
  const breachRate = summary.breach_rate ?? 0;
  const leakRate = summary.leak_rate ?? 0;
  const fieldsLeaked = summary.distinct_fields_leaked ?? [];
  
  return (
    <motion.div
      initial={{ y: 12 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className="card"
    >
      <div className="card-header">
        <ShieldCheck size={18} className="brand-icon" />
        <span className="card-title">Vulnerability Scorecard</span>
      </div>
      <div className="card-body">
        <div className="scorecard-hero">
          <motion.div
            initial={{ scale: 0.92 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.3, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            className="grade-display"
            style={{ color: gradeColor }}
          >
            <div className="grade-value">{grade}</div>
            <div className="grade-label">Campaign Grade</div>
          </motion.div>
          
          <div className="metrics-grid">
            <div className="metric-box">
              <div className="metric-value" style={{ color: gradeColor }}>
                <AnimatedCounter value={summary.max_score ?? 0} />
              </div>
              <div className="metric-label">Vuln Score</div>
            </div>
            <div className="metric-box">
              <div className={`metric-value ${breachRate > 0 ? "danger" : ""}`}>
                <AnimatedCounter value={breachRate * 100} suffix="%" />
              </div>
              <div className="metric-label">Breach Rate</div>
            </div>
            <div className="metric-box">
              <div className="metric-value">
                <AnimatedCounter value={leakRate * 100} suffix="%" />
              </div>
              <div className="metric-label">Leak Rate</div>
            </div>
            <div className="metric-box">
              <div className="metric-value">
                {summary.median_time_to_leak_s != null ? (
                  <AnimatedCounter value={summary.median_time_to_leak_s} suffix="s" />
                ) : "—"}
              </div>
              <div className="metric-label">Median Time-to-Leak</div>
            </div>
          </div>
        </div>
        
        <div className="chip-group">
          <motion.span
            initial={{ scale: 0.94 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.5 }}
            className="chip"
          >
            {summary.total_calls ?? 0} calls total
          </motion.span>

          {(summary.failed_calls ?? 0) > 0 && (
            <motion.span
              initial={{ scale: 0.94 }}
              animate={{ scale: 1 }}
              transition={{ delay: 0.6 }}
              className="chip alert"
            >
              {summary.failed_calls} calls failed
            </motion.span>
          )}

          {fieldsLeaked.map((f, i) => (
            <motion.span
              initial={{ scale: 0.94 }}
              animate={{ scale: 1 }}
              transition={{ delay: 0.7 + (i * 0.1) }}
              className={`chip ${f === "card" ? "alert" : ""}`}
              key={f}
            >
              leaked: {f}
            </motion.span>
          ))}

          {summary.time_note && (
            <motion.span
              initial={{ scale: 0.94 }}
              animate={{ scale: 1 }}
              transition={{ delay: 0.9 }}
              className="chip"
            >
              ⏱ {summary.time_note}
            </motion.span>
          )}
        </div>
      </div>
    </motion.div>
  );
}
