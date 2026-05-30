import { Terminal } from "lucide-react";
import { type Summary } from "../api";
import { motion } from "framer-motion";

interface EvidenceLogProps {
  summary: Summary;
}

export function EvidenceLog({ summary }: EvidenceLogProps) {
  if (summary.evidence_samples.length === 0) return null;

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.2 }}
      className="card"
    >
      <div className="card-header">
        <Terminal size={16} className="brand-icon" />
        <span className="card-title">Breach Evidence Logs</span>
      </div>
      <div className="card-body" style={{ padding: '16px' }}>
        {summary.evidence_samples.map((s, i) => (
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.3 + (i * 0.1) }}
            className="evidence-card" 
            key={i}
          >
            <div className="evidence-header">
              <span className="breach-badge">CRITICAL BREACH</span>
              <span className="evidence-meta">
                {s.attack_id} · Fields: {s.fields.join(", ") || "none"} · {s.turns_to_first_leak ?? "—"} turns
              </span>
            </div>
            <div className="evidence-body">
              <pre>{s.evidence_span}</pre>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
