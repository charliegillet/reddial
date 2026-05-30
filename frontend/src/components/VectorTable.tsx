import { Activity } from "lucide-react";
import { type Summary } from "../api";
import { motion } from "framer-motion";

interface VectorTableProps {
  summary: Summary;
}

export function VectorTable({ summary }: VectorTableProps) {
  const vectors = Object.entries(summary.by_vector).sort((a, b) => b[1].leak_rate - a[1].leak_rate);

  if (vectors.length === 0) return null;

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
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
            const p = Math.round(v.leak_rate * 100);
            const col = v.leak_rate >= 0.5 ? "var(--status-danger)" : v.leak_rate > 0 ? "var(--status-warning)" : "var(--primary-blue)";
            
            return (
              <motion.tr 
                key={id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3, delay: 0.2 + (index * 0.05) }}
              >
                <td className="cell-id">{id}</td>
                <td className="cell-numeric">{v.leaks} / {v.runs}</td>
                <td>
                  <div className="progress-cell">
                    <div className="progress-track">
                      <motion.div 
                        initial={{ width: 0 }}
                        animate={{ width: `${p}%` }}
                        transition={{ duration: 0.8, delay: 0.3 + (index * 0.1), ease: "easeOut" }}
                        className="progress-fill" 
                        style={{ backgroundColor: col }} 
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
