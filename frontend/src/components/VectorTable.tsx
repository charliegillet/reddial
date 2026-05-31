import { Activity } from "lucide-react";
import { type Summary } from "../api";
import { motion } from "framer-motion";

interface VectorTableProps {
  summary: Summary;
}

export function VectorTable({ summary }: VectorTableProps) {
  const vectors = Object.entries(summary.by_vector ?? {}).sort(
    (a, b) => (b[1].leak_rate ?? 0) - (a[1].leak_rate ?? 0)
  );

  if (vectors.length === 0) return null;

  return (
    <motion.div
      initial={{ y: 12 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.4, delay: 0.1 }}
      className="card"
    >
      <div className="card-header">
        <Activity size={16} className="brand-icon" />
        <span className="card-title">Per-Vector Performance</span>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Attack Vector</th>
            <th>Success Rate (Landed)</th>
            <th style={{ width: "40%" }}>Leak Rate Distribution</th>
            <th>Total Breaches</th>
          </tr>
        </thead>
        <tbody>
          {vectors.map(([id, v], index) => {
            const rate = v.leak_rate ?? 0;
            const p = Math.round(rate * 100);
            const col = rate >= 0.5 ? "var(--status-danger)" : rate > 0 ? "var(--status-warning)" : "var(--primary-blue)";
            
            return (
              <motion.tr
                key={id}
                initial={{ x: -8 }}
                animate={{ x: 0 }}
                transition={{ duration: 0.3, delay: 0.2 + (index * 0.05) }}
              >
                <td className="cell-id">{id}</td>
                <td className="cell-numeric">{v.leaks} / {v.runs}</td>
                <td>
                  <div className="progress-cell">
                    <div className="progress-track">
                      <motion.div
                        initial={{ scaleX: 0.001 }}
                        animate={{ scaleX: 1 }}
                        transition={{ duration: 0.8, delay: 0.3 + (index * 0.1), ease: "easeOut" }}
                        className="progress-fill"
                        style={{ width: `${p}%`, transformOrigin: "left", backgroundColor: col }}
                      />
                    </div>
                    <span className="progress-text">{p}%</span>
                  </div>
                </td>
                <td className="cell-numeric">{v.breaches}</td>
              </motion.tr>
            );
          })}
        </tbody>
      </table>
    </motion.div>
  );
}
