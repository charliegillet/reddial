import { useEffect, useRef, useState } from "react";
import { MotionConfig } from "framer-motion";
import {
  Shield,
  LayoutDashboard,
  BarChart3,
  Library as LibraryIcon,
  Settings as SettingsIcon,
  MessagesSquare,
  Bell,
  TrendingDown,
} from "lucide-react";
import { api, type Attack, type Summary } from "./api";
import { Sidebar } from "./components/Sidebar";
import { DashboardView } from "./views/DashboardView";
import { AnalyticsView } from "./views/AnalyticsView";
import { AutoImproveView } from "./views/AutoImproveView";
import { LibraryView } from "./views/LibraryView";
import { SettingsView } from "./views/SettingsView";
import { ConversationView } from "./views/ConversationView";
import "./styles.css";

const GRADE_VAR: Record<string, string> = {
  A: "var(--grade-a)",
  B: "var(--grade-b)",
  C: "var(--grade-c)",
  D: "var(--grade-d)",
  F: "var(--grade-f)",
};

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

type ViewId =
  | "dashboard"
  | "conversation"
  | "analytics"
  | "auto-improve"
  | "library"
  | "settings";

const NAV: { id: ViewId; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "dashboard", label: "Threat Console", icon: LayoutDashboard },
  { id: "conversation", label: "Conversation", icon: MessagesSquare },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
  { id: "auto-improve", label: "Auto-Improve", icon: TrendingDown },
  { id: "library", label: "Attack Library", icon: LibraryIcon },
  { id: "settings", label: "Settings", icon: SettingsIcon },
];

export function App() {
  const [health, setHealth] = useState<"up" | "down" | "?">("?");
  const [version, setVersion] = useState<string>("");
  const [attacks, setAttacks] = useState<Attack[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [n, setN] = useState(36);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<ViewId>("dashboard");
  const [bellOpen, setBellOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.health().then((h) => { setHealth("up"); setVersion(h.version); }).catch(() => setHealth("down"));
    api.attacks().then((r) => setAttacks(r.attacks)).catch(() => {});
    api.scorecardLatest().then(setSummary).catch(() => {});
  }, []);

  useEffect(() => {
    if (!bellOpen) return;
    function onClick(e: MouseEvent) {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) setBellOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [bellOpen]);

  async function runScan() {
    // Always surface the result: jump to the Dashboard so the scanning state +
    // scorecard are visible no matter which view Launch was clicked from.
    setActiveView("dashboard");
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
  const activeLabel = NAV.find((v) => v.id === activeView)?.label ?? "Threat Console";

  const breachCount = summary
    ? Math.round((summary.breach_rate ?? 0) * (summary.total_calls ?? 0))
    : 0;

  return (
    <MotionConfig reducedMotion="user">
    <div className="app-container">
      {/* ── Global Nav Rail ── */}
      <nav className="nav-rail">
        <div className="rail-brand">
          <div className="brand-orb"><Shield size={18} strokeWidth={2.5} /></div>
        </div>
        <div className="rail-links">
          {NAV.filter((v) => v.id !== "settings").map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              className={`rail-item ${activeView === id ? "active" : ""}`}
              aria-label={label}
              aria-current={activeView === id ? "page" : undefined}
              title={label}
              onClick={() => setActiveView(id)}
            >
              <Icon size={20} />
            </button>
          ))}
        </div>
        <div className="rail-bottom">
          <button
            type="button"
            className={`rail-item ${activeView === "settings" ? "active" : ""}`}
            aria-label="Settings"
            aria-current={activeView === "settings" ? "page" : undefined}
            title="Settings"
            onClick={() => setActiveView("settings")}
          >
            <SettingsIcon size={20} />
          </button>
        </div>
      </nav>

      <div className="app-main">
        {/* ── Header ── */}
        <header className="topbar">
          <div className="topbar-left">
            <h1>Workspace / <span>{activeLabel}</span></h1>
          </div>
          <div className="topbar-right">
            <div className="health-status">
              <span className={`health-indicator ${health === "up" ? "up" : health === "down" ? "down" : ""}`} />
              {health === "up" ? `API Online · v${version}` : health === "down" ? "API Offline" : "Connecting..."}
            </div>

            <div className="bell-wrap" ref={bellRef}>
              <button
                type="button"
                className="icon-btn"
                aria-label="Notifications"
                aria-haspopup="true"
                aria-expanded={bellOpen}
                onClick={() => setBellOpen((o) => !o)}
              >
                <Bell size={18} />
                {breachCount > 0 && <span className="bell-dot" aria-hidden="true" />}
              </button>
              {bellOpen && (
                <div className="bell-popover" role="dialog" aria-label="Notifications">
                  <div className="bell-popover-header">Latest Run</div>
                  {summary ? (
                    <div className="bell-popover-body">
                      <div className={`bell-item ${breachCount > 0 ? "alert" : ""}`}>
                        <span className="bell-item-count">{breachCount}</span>
                        <span className="bell-item-label">
                          {breachCount === 1 ? "breach" : "breaches"} across {summary.total_calls} calls
                        </span>
                      </div>
                      {summary.run_id && (
                        <div className="bell-item-meta">run {summary.run_id}</div>
                      )}
                    </div>
                  ) : (
                    <div className="bell-popover-body">
                      <div className="bell-item-meta">No runs yet.</div>
                    </div>
                  )}
                </div>
              )}
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

          {/* ── Main Content (view router) ── */}
          <main className="dashboard-content">
            <div className="content-wrapper">
              {activeView === "dashboard" && (
                <DashboardView
                  summary={summary}
                  running={running}
                  gradeColor={gradeColor}
                  runScan={runScan}
                />
              )}
              {activeView === "conversation" && <ConversationView summary={summary} />}
              {activeView === "analytics" && <AnalyticsView />}
              {activeView === "auto-improve" && <AutoImproveView />}
              {activeView === "library" && <LibraryView attacks={attacks} />}
              {activeView === "settings" && (
                <SettingsView apiBase={API_BASE} version={version} health={health} />
              )}
            </div>
          </main>
        </div>
      </div>
    </div>
    </MotionConfig>
  );
}
