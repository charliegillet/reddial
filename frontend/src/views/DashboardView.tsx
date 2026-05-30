import { ShieldAlert, Activity } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { type Summary } from "../api";
import { ScorecardSummary } from "../components/ScorecardSummary";
import { VectorTable } from "../components/VectorTable";
import { EvidenceLog } from "../components/EvidenceLog";
import { ScanningScreen } from "../components/ScanningScreen";

interface DashboardViewProps {
  summary: Summary | null;
  running: boolean;
  gradeColor: string;
  runScan: () => void;
}

export function DashboardView({ summary, running, gradeColor, runScan }: DashboardViewProps) {
  return (
    <>
      <motion.div
        initial={{ y: -8 }}
        animate={{ y: 0 }}
        className="safety-banner"
      >
        <div className="banner-icon"><ShieldAlert size={20} /></div>
        <div className="banner-text">
          <p><strong>SYNTHETIC DATA HARNESS</strong></p>
          <p>All operations utilize fake PII (Stripe test BINs, specimen SSNs). Runs offline loopback against mock endpoints. No live dialing or real-world PII exposure from this console.</p>
        </div>
      </motion.div>

      <AnimatePresence mode="wait">
        {running ? (
          <ScanningScreen key="scanning" />
        ) : !summary ? (
          <motion.div
            key="empty"
            initial={{ opacity: 1 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="card empty-onboarding"
          >
            <div className="empty-state">
              <div className="empty-icon-wrap">
                <Activity size={32} />
              </div>
              <h3>Ready for your first campaign</h3>
              <p>Run a deterministic attacker FSM against your mock voice agent to generate a vulnerability scorecard. No configuration required.</p>
              <button className="primary-button inline-btn" onClick={runScan}>
                Launch Campaign Now
              </button>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="results"
            style={{ display: "flex", flexDirection: "column", gap: "24px" }}
          >
            <ScorecardSummary summary={summary} gradeColor={gradeColor} />
            <VectorTable summary={summary} />
            <EvidenceLog summary={summary} />
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
