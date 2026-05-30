import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TrendingDown, ShieldAlert, Activity, Play, Loader2 } from "lucide-react";
import { api, type AutoImproveResult } from "../api";
import { ImprovementCurve } from "../components/ImprovementCurve";

function pct(v: number | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${Math.round(v * 100)}%`;
}

// Truncate a long guardrail clause for inline table display; full text on hover.
function truncate(s: string, max = 80): string {
  if (!s) return "—";
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

// Color the per-round breach-rate cell on a danger→success ramp.
function rampColor(rate: number): string {
  if (rate <= 0) return "var(--status-success)";
  if (rate >= 0.5) return "var(--status-danger)";
  return "var(--status-warning)";
}

export function AutoImproveView() {
  const [result, setResult] = useState<AutoImproveResult | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [rounds, setRounds] = useState(5);
  const [nPerRound, setNPerRound] = useState(24);

  // Self-fetching like AnalyticsView: pull the latest run on mount.
  useEffect(() => {
    api
      .autoImproveLatest()
      .then(setResult)
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  async function run() {
    setRunning(true);
    setErr(null);
    try {
      const r = await api.runAutoImprove(rounds, nPerRound, 0);
      setResult(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  const has = result != null;

  return (
    <motion.div
      initial={{ y: 10 }}
      animate={{ y: 0 }}
      style={{ display: "flex", flexDirection: "column", gap: "24px" }}
    >
      {/* Honest banner — scope is explicit, no overclaim. */}
      <div className="safety-banner">
        <ShieldAlert size={20} style={{ flexShrink: 0, marginTop: 2 }} />
        <p>
          <strong>HONEST SCOPE</strong>
          This loop improves OUR mock target vs OUR fixed 12-attack suite — it is
          NOT a measure of general robustness. A held-out vector is probed to
          prove it does not magically generalize.
        </p>
      </div>

      {/* Controls */}
      <div className="card">
        <div className="card-header">
          <TrendingDown size={18} className="brand-icon" />
          <span className="card-title">Auto-Improve Loop</span>
        </div>
        <div className="card-body">
          <div className="auto-improve-controls">
            <div className="ai-control">
              <label htmlFor="ai-rounds">Rounds</label>
              <input
                id="ai-rounds"
                className="number-input"
                type="number"
                min={1}
                max={10}
                value={rounds}
                onChange={(e) =>
                  setRounds(Math.max(1, Math.min(10, Number(e.target.value) || 1)))
                }
                disabled={running}
              />
            </div>
            <div className="ai-control">
              <label htmlFor="ai-n">Calls / round</label>
              <input
                id="ai-n"
                className="number-input"
                type="number"
                min={1}
                max={100}
                value={nPerRound}
                onChange={(e) =>
                  setNPerRound(Math.max(1, Math.min(100, Number(e.target.value) || 1)))
                }
                disabled={running}
              />
            </div>
            <button
              type="button"
              className="primary-button inline-btn"
              onClick={run}
              disabled={running}
            >
              {running ? (
                <>
                  <Loader2 size={16} className="spin" /> Running…
                </>
              ) : (
                <>
                  <Play size={16} /> Run Loop
                </>
              )}
            </button>
          </div>
          {err && (
            <div className="error-msg" style={{ marginTop: 16 }}>
              {err}
            </div>
          )}
        </div>
      </div>

      {!has ? (
        <div className="card">
          <div className="card-body">
            <div className="view-empty">
              <Activity size={28} />
              <p>
                {loaded
                  ? "No auto-improve run yet. Set rounds and calls, then Run Loop."
                  : "Loading latest auto-improve run…"}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <>
          {/* (a) Curve + start→final boxes + rounds-to-converge */}
          <div className="card">
            <div className="card-header">
              <TrendingDown size={16} className="brand-icon" />
              <span className="card-title">Improvement Curve</span>
            </div>
            <div className="card-body">
              <ImprovementCurve curve={result!.curve} />
              <div className="metrics-grid" style={{ marginTop: 24 }}>
                <div className="metric-box">
                  <div className="metric-value danger">
                    {pct(result!.start.breach_rate)}
                  </div>
                  <div className="metric-label">Start Breach Rate</div>
                </div>
                <div className="metric-box">
                  <div
                    className={`metric-value ${result!.final.breach_rate > 0 ? "danger" : ""}`}
                  >
                    {pct(result!.final.breach_rate)}
                  </div>
                  <div className="metric-label">Final Breach Rate</div>
                </div>
                <div className="metric-box">
                  <div className="metric-value">
                    {result!.improvement.rounds_to_converge}
                  </div>
                  <div className="metric-label">Rounds to Converge</div>
                </div>
                <div className="metric-box">
                  <div className="metric-value mono-value">
                    {result!.converged_reason}
                  </div>
                  <div className="metric-label">Converged Reason</div>
                </div>
              </div>
            </div>
          </div>

          {/* (b) Per-round trajectory table */}
          <div className="card">
            <div className="card-header">
              <Activity size={16} className="brand-icon" />
              <span className="card-title">Per-Round Trajectory</span>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Round</th>
                  <th>Breach Rate</th>
                  <th style={{ width: "40%" }}>Clause Added</th>
                  <th>Newly Blocked</th>
                </tr>
              </thead>
              <tbody>
                {result!.trajectory.map((rec, i) => {
                  const rate = rec.summary?.breach_rate ?? 0;
                  return (
                    <motion.tr
                      key={rec.round}
                      initial={{ x: -8 }}
                      animate={{ x: 0 }}
                      transition={{ duration: 0.3, delay: 0.05 * i }}
                    >
                      <td className="cell-id">R{rec.round}</td>
                      <td className="cell-numeric" style={{ color: rampColor(rate) }}>
                        {pct(rate)}
                      </td>
                      <td className="cell-template">
                        {rec.clause_added ? (
                          (() => {
                            // clause_added is the clause id (string); the full text is the
                            // last entry appended to this round's guardrail_clauses.
                            const clauseText =
                              rec.guardrail_clauses?.[rec.guardrail_clauses.length - 1] ??
                              rec.clause_added;
                            const showText = clauseText && clauseText !== rec.clause_added;
                            return (
                              <span title={clauseText}>
                                <span className="cell-id">{rec.clause_added}</span>
                                {showText ? ` — ${truncate(clauseText)}` : ""}
                              </span>
                            );
                          })()
                        ) : (
                          "— (baseline / converged)"
                        )}
                      </td>
                      <td>
                        <div className="chip-group" style={{ marginTop: 0 }}>
                          {(rec.vectors_newly_blocked ?? []).length > 0 ? (
                            rec.vectors_newly_blocked.map((v) => (
                              <span key={v} className="chip success">
                                {v}
                              </span>
                            ))
                          ) : (
                            <span className="cell-numeric">—</span>
                          )}
                        </div>
                      </td>
                    </motion.tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* (c) Final hardened guardrail */}
          <div className="card">
            <div className="card-header">
              <ShieldAlert size={16} className="brand-icon" />
              <span className="card-title">Final Hardened Guardrail</span>
            </div>
            <div className="card-body">
              <pre className="guardrail-pre">
                {result!.final_guardrail.join("\n")}
              </pre>
            </div>
          </div>

          {/* (d) Held-out result, stated plainly */}
          <div className="card">
            <div className="card-header">
              <ShieldAlert size={16} className="brand-icon" />
              <span className="card-title">Held-Out Probe</span>
            </div>
            <div className="card-body">
              <p className="held-out-statement">
                Held-out <code>{result!.held_out.vector}</code>{" "}
                {result!.held_out.breach_after ? (
                  <>
                    still leaks after convergence (breach before:{" "}
                    {String(result!.held_out.breach_before)}, after:{" "}
                    {String(result!.held_out.breach_after)}) — the loop did NOT
                    generalize to a vector it never trained on. That is the honest
                    proof: it hardens OUR target against OUR known suite, not the
                    open world.
                  </>
                ) : (
                  <>
                    did not breach after convergence (before:{" "}
                    {String(result!.held_out.breach_before)}, after:{" "}
                    {String(result!.held_out.breach_after)}).
                  </>
                )}
              </p>
              <p className="helper-text">{result!.honest_note}</p>
              <p className="helper-text">{result!.time_note}</p>
            </div>
          </div>
        </>
      )}
    </motion.div>
  );
}
