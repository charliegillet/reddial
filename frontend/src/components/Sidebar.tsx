import { Activity, Terminal, AlertTriangle, Play } from "lucide-react";
import { type Attack } from "../api";

interface SidebarProps {
  n: number;
  setN: (n: number) => void;
  runScan: () => void;
  running: boolean;
  health: "up" | "down" | "?";
  err: string | null;
  attacks: Attack[];
}

export function Sidebar({ n, setN, runScan, running, health, err, attacks }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-section">
        <h2 className="section-header">
          <Play size={14} /> Run Campaign
        </h2>
        <div className="control-group">
          <label htmlFor="n">Loopback Iterations</label>
          <input 
            id="n" 
            type="number" 
            className="number-input"
            min={1} 
            max={500} 
            value={n}
            onChange={(e) => setN(Math.max(1, Math.min(500, Number(e.target.value) || 1)))} 
            disabled={running}
          />
          <p className="helper-text">
            Drives deterministic attacker FSM against mock target to generate scorecard.
          </p>
        </div>
        <button className="primary-button" onClick={runScan} disabled={running || health !== "up"}>
          {running ? <Activity size={16} className="animate-spin" /> : <Terminal size={16} />}
          {running ? "Executing Campaign..." : "Launch Campaign"}
        </button>
        {err && (
          <div className="error-msg">
            <AlertTriangle size={14} /> {err}
          </div>
        )}
      </div>

      <div className="sidebar-section">
        <h2 className="section-header">
          <Database size={14} /> Attack Library ({attacks.length})
        </h2>
        <div className="attack-list">
          {attacks.length === 0 && (
            <div className="empty-state" style={{ padding: '24px 0' }}>No attacks loaded</div>
          )}
          {attacks.map((a) => (
            <div className="attack-item" key={a.id}>
              <div className="attack-meta">
                <span className="attack-id">{a.id}</span>
                <span className="attack-category">{a.category}</span>
              </div>
              <div className="attack-template">"{a.spoken_template}"</div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}

function Database(props: any) {
  return (
    <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M3 5V19A9 3 0 0 0 21 19V5" />
      <path d="M3 12A9 3 0 0 0 21 12" />
    </svg>
  );
}
