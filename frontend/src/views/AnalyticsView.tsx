import { useCallback, useEffect, useState } from "react";
import { BarChart3, History, Activity, AlertTriangle } from "lucide-react";
import { motion } from "framer-motion";
import { api, type Metrics, type RunSummary } from "../api";

// metrics()/scans() are provided by the data teammate's ./api client.
// We still access them defensively so this view renders gracefully if a
// method or its data is absent at runtime.
type CampaignMetrics = Metrics;
type ScanSummaryRow = RunSummary;

type MaybeAnalyticsApi = {
  metrics?: () => Promise<CampaignMetrics>;
  scans?: () => Promise<ScanSummaryRow[] | { runs?: ScanSummaryRow[]; scans?: ScanSummaryRow[] }>;
};

function pct(v: number | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${Math.round(v * 100)}%`;
}

export function AnalyticsView() {
  const [metrics, setMetrics] = useState<CampaignMetrics | null>(null);
  const [scans, setScans] = useState<ScanSummaryRow[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  // Track whether *both* fetches failed so we can distinguish "API errored"
  // from the legitimate "no runs yet" empty state.
  const [errored, setErrored] = useState(false);

  const load = useCallback(() => {
    setLoaded(false);
    setErrored(false);
    const a = api as unknown as MaybeAnalyticsApi;
    const tasks: Promise<unknown>[] = [];

    if (typeof a.metrics === "function") {
      tasks.push(a.metrics().then(setMetrics));
    }
    if (typeof a.scans === "function") {
      tasks.push(
        a.scans().then((r) => setScans(Array.isArray(r) ? r : r.runs ?? r.scans ?? []))
      );
    }
    Promise.allSettled(tasks).then((results) => {
      // Only flag an error banner if every attempted fetch rejected (a partial
      // success still renders whatever data we got).
      const attempted = results.length;
      const rejected = results.filter((r) => r.status === "rejected").length;
      setErrored(attempted > 0 && rejected === attempted);
      setLoaded(true);
    });
  }, []);

  useEffect(() => { load(); }, [load]);

  const hasMetrics = metrics != null;
  const hasScans = scans != null && scans.length > 0;

  return (
    <motion.div
      initial={{ y: 10 }}
      animate={{ y: 0 }}
      style={{ display: "flex", flexDirection: "column", gap: "24px" }}
    >
      {errored && (
        <div className="error-msg" role="alert">
          <AlertTriangle size={14} />
          <span>
            Couldn't load analytics from the control-plane.
            <button type="button" className="retry-button" onClick={load}>
              Retry
            </button>
          </span>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <BarChart3 size={18} className="brand-icon" />
          <span className="card-title">Campaign Metrics</span>
        </div>
        <div className="card-body">
          {hasMetrics ? (
            <div className="metrics-grid">
              <div className="metric-box">
                <div className="metric-value">{metrics!.scans_run}</div>
                <div className="metric-label">Scans Run</div>
              </div>
              <div className="metric-box">
                <div className={`metric-value ${metrics!.last_breach_rate > 0 ? "danger" : ""}`}>
                  {pct(metrics!.last_breach_rate)}
                </div>
                <div className="metric-label">Last Breach Rate</div>
              </div>
              <div className="metric-box">
                <div className="metric-value mono-value">
                  {metrics!.last_run_id ?? "—"}
                </div>
                <div className="metric-label">Last Run ID</div>
              </div>
            </div>
          ) : (
            <div className="view-empty">
              <Activity size={28} />
              <p>{loaded ? "No campaign metrics available yet. Run a campaign from the Dashboard." : "Loading metrics…"}</p>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <History size={16} className="brand-icon" />
          <span className="card-title">Recent Run History</span>
        </div>
        {hasScans ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Calls</th>
                <th>Breach Rate</th>
                <th>Leak Rate</th>
                <th>Grade</th>
              </tr>
            </thead>
            <tbody>
              {scans!.map((s, i) => (
                <motion.tr
                  key={s.run_id ?? i}
                  initial={{ x: -8 }}
                  animate={{ x: 0 }}
                  transition={{ duration: 0.3, delay: 0.05 * i }}
                >
                  <td className="cell-id">{s.run_id ?? "—"}</td>
                  <td className="cell-numeric">{s.total_calls ?? "—"}</td>
                  <td className="cell-numeric">{pct(s.breach_rate)}</td>
                  <td className="cell-numeric">{pct(s.leak_rate)}</td>
                  <td className="cell-numeric">{s.max_grade ?? "—"}</td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="card-body">
            <div className="view-empty">
              <History size={28} />
              <p>{loaded ? "No runs yet." : "Loading run history…"}</p>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
