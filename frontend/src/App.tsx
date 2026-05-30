import { useEffect, useState } from "react";
import { ShieldAlert, LayoutDashboard, Shield, BarChart3, Settings, Users, Bell, Activity } from "lucide-react";
import { api, type Attack, type Summary } from "./api";
import { Sidebar } from "./components/Sidebar";
import { ScorecardSummary } from "./components/ScorecardSummary";
import { VectorTable } from "./components/VectorTable";
import { EvidenceLog } from "./components/EvidenceLog";
import { ScanningScreen } from "./components/ScanningScreen";
import { motion, AnimatePresence } from "framer-motion";
import "./styles.css";

const GRADE_VAR: Record<string, string> = {
  A: "var(--grade-a)", 
  B: "var(--grade-b)", 
  C: "var(--grade-c)", 
  D: "var(--grade-d)", 
  F: "var(--grade-f)",
};

export function App() {
  const [health, setHealth] = useState<"up" | "down" | "?">("?");
  const [version, setVersion] = useState<string>("");
  const [attacks, setAttacks] = useState<Attack[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [n, setN] = useState(36);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.health().then((h) => { setHealth("up"); setVersion(h.version); }).catch(() => setHealth("down"));
    api.attacks().then((r) => setAttacks(r.attacks)).catch(() => {});
    api.scorecardLatest().then(setSummary).catch(() => {});
  }, []);

  async function runScan() {
    setRunning(true); 
    setErr(null);
    try {
      const { summary } = await api.runScan(n, 4);
      setSummary(summary);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  const gradeColor = GRADE_VAR[summary?.max_grade ?? ""] ?? "var(--text-tertiary)";

  return (
    <div className="app-container">
      {/* ── Global Nav Rail ── */}
      <nav className="nav-rail">
        <div className="rail-brand">
          <div className="brand-orb"><Shield size={18} strokeWidth={2.5} /></div>
        </div>
        <div className="rail-links">
          <a href="#" className="rail-item active"><LayoutDashboard size={20} /></a>
          <a href="#" className="rail-item"><BarChart3 size={20} /></a>
          <a href="#" className="rail-item"><Users size={20} /></a>
        </div>
        <div className="rail-bottom">
          <a href="#" className="rail-item"><Settings size={20} /></a>
        </div>
      </nav>

      <div className="app-main">
        {/* ── Header ── */}
        <header className="topbar">
          <div className="topbar-left">
            <h1>Workspace / <span>Threat Console</span></h1>
          </div>
          <div className="topbar-right">
            <div className="health-status">
              <span className={`health-indicator ${health === "up" ? "up" : health === "down" ? "down" : ""}`} />
              {health === "up" ? `API Online · v${version}` : health === "down" ? "API Offline" : "Connecting..."}
            </div>
            <button className="icon-btn"><Bell size={18} /></button>
            <div className="user-avatar">
              <img src="https://api.dicebear.com/7.x/notionists/svg?seed=Felix" alt="User" />
            </div>
          </div>
        </header>

        {/* ── Main Layout ── */}
        <div className="main-layout">
          <Sidebar 
            n={n} 
            setN={setN} 
            runScan={runScan} 
            running={running} 
            health={health} 
            err={err} 
            attacks={attacks} 
          />

          {/* ── Main Dashboard ── */}
          <main className="dashboard-content">
            <div className="content-wrapper">
              
              <motion.div 
                initial={{ opacity: 0, y: -10 }} 
                animate={{ opacity: 1, y: 0 }} 
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
                    initial={{ opacity: 0 }}
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

            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
