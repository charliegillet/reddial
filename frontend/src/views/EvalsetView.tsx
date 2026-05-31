import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ClipboardCheck,
  CheckCircle2,
  XCircle,
  Play,
  Loader2,
  Sparkles,
  ShieldCheck,
} from "lucide-react";
import {
  api,
  type EvalsetScenario,
  type EvalsetResult,
  type ImproveResult,
} from "../api";

function pct(v: number | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${Math.round(v * 100)}%`;
}

// Breach rate for one evalset run: breaches across all scenario attempts.
function breachRate(r: EvalsetResult | undefined): number {
  if (!r) return 0;
  const scenarios = r.scenarios ?? [];
  const attempts = scenarios.reduce((acc, s) => acc + (s.runs ?? 0), 0);
  if (attempts <= 0) return 0;
  return (r.total_breaches ?? 0) / attempts;
}

// Inline SVG of per-round breach rate descending toward a PASS. Self-contained
// (the shared ImprovementCurve takes the auto-improve parallel-array shape).
// Visibility is never gated on opacity: the polyline draws at full opacity and
// framer-motion only animates pathLength as a flourish.
function BreachCurve({ rounds }: { rounds: ImproveResult["rounds"] }) {
  const list = rounds ?? [];
  const rates = list.map((r) => breachRate(r.evalset));
  const n = rates.length;

  if (n < 2) {
    return (
      <div className="improvement-curve">
        <div className="view-empty" style={{ padding: "32px 24px" }}>
          <p>Need at least two rounds to plot the breach-rate curve.</p>
        </div>
        <p className="curve-caption">breach rate vs the basic evalset, per round</p>
      </div>
    );
  }

  const W = 640;
  const H = 220;
  const padL = 44;
  const padR = 20;
  const padT = 20;
  const padB = 36;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const maxRate = Math.max(...rates, 0.0001);
  const x = (i: number) => padL + (n === 1 ? 0 : (i / (n - 1)) * plotW);
  const y = (r: number) => padT + (1 - r / maxRate) * plotH;

  const points = rates.map((r, i) => [x(i), y(r)]);
  const polyPoints = points.map(([px, py]) => `${px},${py}`).join(" ");
  const baselineY = y(rates[0]);

  return (
    <div className="improvement-curve">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label="Breach rate per round, descending = improving toward a PASS"
        preserveAspectRatio="xMidYMid meet"
      >
        <line x1={padL} y1={padT} x2={padL} y2={padT + plotH} stroke="var(--glass-border)" strokeWidth={1} />
        <line x1={padL} y1={padT + plotH} x2={padL + plotW} y2={padT + plotH} stroke="var(--glass-border)" strokeWidth={1} />
        <line
          x1={padL}
          y1={baselineY}
          x2={padL + plotW}
          y2={baselineY}
          stroke="var(--status-danger)"
          strokeWidth={1}
          strokeDasharray="4 4"
          opacity={0.5}
        />
        <text x={padL + 4} y={baselineY - 6} fill="var(--text-faint)" fontSize={10} fontFamily="var(--font-mono)">
          baseline {Math.round(rates[0] * 100)}%
        </text>
        <motion.polyline
          points={polyPoints}
          fill="none"
          stroke="var(--accent-acid)"
          strokeWidth={2.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.9, ease: "easeOut" }}
          style={{ filter: "drop-shadow(0 0 6px var(--accent-acid-dim))" }}
        />
        {points.map(([px, py], i) => (
          <g key={i}>
            <circle
              cx={px}
              cy={py}
              r={4}
              fill="var(--bg-color)"
              stroke={list[i]?.evalset?.passed ? "var(--status-success)" : "var(--accent-acid)"}
              strokeWidth={2}
            />
            <text
              x={px}
              y={padT + plotH + 18}
              fill="var(--text-faint)"
              fontSize={10}
              fontFamily="var(--font-mono)"
              textAnchor="middle"
            >
              R{list[i]?.round ?? i}
            </text>
          </g>
        ))}
      </svg>
      <p className="curve-caption">breach rate vs the basic evalset, per round</p>
    </div>
  );
}

// One scenario row: green when passed, red when breaching.
function ScenarioRow({
  scenario,
  result,
  index,
}: {
  scenario: EvalsetScenario;
  result?: EvalsetResult["scenarios"][number];
  index: number;
}) {
  const passed = result?.passed;
  return (
    <motion.tr
      initial={{ x: -8 }}
      animate={{ x: 0 }}
      transition={{ duration: 0.3, delay: 0.05 * index }}
    >
      <td className="cell-id">{scenario.id}</td>
      <td className="cell-id">{scenario.attack_id}</td>
      <td className="cell-template" title={scenario.description}>
        {scenario.description || "—"}
        <div className="helper-text" style={{ marginTop: 4 }}>
          pass if: {scenario.pass_criterion || "—"}
        </div>
      </td>
      <td className="cell-numeric">
        {result ? `${result.breaches}/${result.runs}` : "—"}
      </td>
      <td>
        {result == null ? (
          <span className="cell-numeric">—</span>
        ) : passed ? (
          <span className="chip success">
            <CheckCircle2 size={12} /> PASS
          </span>
        ) : (
          <span className="chip danger">
            <XCircle size={12} /> BREACH
          </span>
        )}
      </td>
    </motion.tr>
  );
}

export function EvalsetView() {
  const [scenarios, setScenarios] = useState<EvalsetScenario[]>([]);
  const [latest, setLatest] = useState<EvalsetResult | null>(null);
  const [improve, setImprove] = useState<ImproveResult | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [improving, setImproving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .evalset()
      .then((r) => {
        setScenarios(r.evalset ?? []);
        setLatest(r.latest ?? null);
      })
      .catch((e) => setLoadErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoaded(true));
  }, []);

  async function runOnce() {
    setRunning(true);
    setErr(null);
    try {
      const r = await api.runEvalset();
      setLatest(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  async function runImprove() {
    setImproving(true);
    setErr(null);
    try {
      const r = await api.improveEvalset();
      setImprove(r);
      // Surface the final round as the "latest" per-scenario result too.
      const lastRound = (r.rounds ?? [])[(r.rounds ?? []).length - 1];
      if (lastRound?.evalset) setLatest(lastRound.evalset);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setImproving(false);
    }
  }

  // Index per-scenario results by scenario id for row lookup.
  const resultById = new Map(
    (latest?.scenarios ?? []).map((s) => [s.id, s]),
  );
  const busy = running || improving;
  const hasScenarios = scenarios.length > 0;

  return (
    <motion.div
      initial={{ y: 10 }}
      animate={{ y: 0 }}
      style={{ display: "flex", flexDirection: "column", gap: "24px" }}
    >
      {/* Controls */}
      <div className="card">
        <div className="card-header">
          <ClipboardCheck size={18} className="brand-icon" />
          <span className="card-title">Basic Evalset</span>
          {latest && (
            <span
              className={`chip ${latest.passed ? "success" : "danger"}`}
              style={{ marginLeft: "auto" }}
            >
              {latest.passed ? "PASSING" : "FAILING"} · {pct(latest.pass_rate)}
            </span>
          )}
        </div>
        <div className="card-body">
          <p className="helper-text" style={{ marginBottom: 16 }}>
            A fixed suite of attack scenarios, each with a pass criterion. Run it to
            see which scenarios the agent holds, then watch the breach rate fall to
            a PASS as it self-improves.
          </p>
          <div className="auto-improve-controls">
            <button
              type="button"
              className="primary-button inline-btn"
              onClick={runOnce}
              disabled={busy}
            >
              {running ? (
                <>
                  <Loader2 size={16} className="spin" /> Running…
                </>
              ) : (
                <>
                  <Play size={16} /> Run evalset
                </>
              )}
            </button>
            <button
              type="button"
              className="primary-button inline-btn"
              onClick={runImprove}
              disabled={busy}
            >
              {improving ? (
                <>
                  <Loader2 size={16} className="spin" /> Improving…
                </>
              ) : (
                <>
                  <Sparkles size={16} /> Run auto-improve until it passes
                </>
              )}
            </button>
          </div>
          {err && (
            <div className="error-msg" role="alert" style={{ marginTop: 16 }}>
              {err}
            </div>
          )}
          {loadErr && !err && (
            <div className="error-msg" role="alert" style={{ marginTop: 16 }}>
              Could not load evalset: {loadErr}
            </div>
          )}
        </div>
      </div>

      {/* The "magic": breach-rate curve dropping to PASS */}
      {improve && (
        <>
          <div className="card">
            <div className="card-header">
              <Sparkles size={16} className="brand-icon" />
              <span className="card-title">The Magic — Breach Rate → PASS</span>
              <span
                className={`chip ${improve.passed ? "success" : "danger"}`}
                style={{ marginLeft: "auto" }}
              >
                {improve.passed
                  ? `PASSED in ${improve.rounds_to_pass ?? "?"} round${improve.rounds_to_pass === 1 ? "" : "s"}`
                  : "did not pass"}
              </span>
            </div>
            <div className="card-body">
              <BreachCurve rounds={improve.rounds} />
              <table className="data-table" style={{ marginTop: 24 }}>
                <thead>
                  <tr>
                    <th>Round</th>
                    <th>Breach Rate</th>
                    <th>Pass Rate</th>
                    <th style={{ width: "45%" }}>Guardrail Added</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {(improve.rounds ?? []).map((rec, i) => {
                    const rate = breachRate(rec.evalset);
                    return (
                      <motion.tr
                        key={rec.round}
                        initial={{ x: -8 }}
                        animate={{ x: 0 }}
                        transition={{ duration: 0.3, delay: 0.05 * i }}
                      >
                        <td className="cell-id">R{rec.round}</td>
                        <td
                          className="cell-numeric"
                          style={{
                            color: rate <= 0 ? "var(--status-success)" : "var(--status-danger)",
                          }}
                        >
                          {pct(rate)}
                        </td>
                        <td className="cell-numeric">{pct(rec.evalset?.pass_rate)}</td>
                        <td className="cell-template" title={rec.guardrail_added ?? undefined}>
                          {rec.guardrail_added || "— (baseline)"}
                        </td>
                        <td>
                          {rec.evalset?.passed ? (
                            <span className="chip success">
                              <CheckCircle2 size={12} /> PASS
                            </span>
                          ) : (
                            <span className="chip danger">
                              <XCircle size={12} /> FAIL
                            </span>
                          )}
                        </td>
                      </motion.tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Held-out probe — the credible "magic": this vector was NEVER
              trained, so it STAYS RED while the trained ones go green. */}
          {improve.held_out && (
            <div className="card">
              <div className="card-header">
                <ShieldCheck size={16} className="brand-icon" />
                <span className="card-title">Held-out probe (honest)</span>
                <span
                  className={`chip ${improve.held_out.still_breaches ? "danger" : "success"}`}
                  style={{ marginLeft: "auto" }}
                >
                  {improve.held_out.still_breaches ? (
                    <>
                      <XCircle size={12} /> held-out — not trained, still breaches (honest)
                    </>
                  ) : (
                    <>
                      <CheckCircle2 size={12} /> held-out blocked
                    </>
                  )}
                </span>
              </div>
              <div className="card-body">
                <p className="helper-text" style={{ marginBottom: 12 }}>
                  The <code>{improve.held_out.attack_id}</code> (social_pressure)
                  scenario is HELD OUT of training — the loop never adds the clause
                  that would close it. It stays red on purpose: proof the loop does
                  not magically generalise to a vector it never trained on.
                </p>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Scenario</th>
                      <th>Attack</th>
                      <th>Breaches before</th>
                      <th>Breaches after</th>
                      <th>Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="cell-id">{improve.held_out.scenario_id}</td>
                      <td className="cell-id">{improve.held_out.attack_id}</td>
                      <td className="cell-numeric">{improve.held_out.breaches_before}</td>
                      <td className="cell-numeric">{improve.held_out.breaches_after}</td>
                      <td>
                        <span
                          className={`chip ${improve.held_out.still_breaches ? "danger" : "success"}`}
                        >
                          {improve.held_out.still_breaches ? (
                            <>
                              <XCircle size={12} /> BREACH
                            </>
                          ) : (
                            <>
                              <CheckCircle2 size={12} /> PASS
                            </>
                          )}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Honest note — prominent. */}
          <div className="safety-banner">
            <ShieldCheck size={20} style={{ flexShrink: 0, marginTop: 2 }} />
            <p>
              <strong>HONEST NOTE</strong>
              {improve.honest_note || "—"}
            </p>
          </div>

          {(improve.final_guardrail ?? []).length > 0 && (
            <div className="card">
              <div className="card-header">
                <ShieldCheck size={16} className="brand-icon" />
                <span className="card-title">Final Guardrail</span>
              </div>
              <div className="card-body">
                <pre className="guardrail-pre">
                  {(improve.final_guardrail ?? []).join("\n")}
                </pre>
              </div>
            </div>
          )}
        </>
      )}

      {/* Scenario table */}
      <div className="card">
        <div className="card-header">
          <ClipboardCheck size={16} className="brand-icon" />
          <span className="card-title">Scenarios ({scenarios.length})</span>
        </div>
        {hasScenarios ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Attack</th>
                <th style={{ width: "45%" }}>Description</th>
                <th>Breaches</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s, i) => (
                <ScenarioRow
                  key={s.id}
                  scenario={s}
                  result={resultById.get(s.id)}
                  index={i}
                />
              ))}
            </tbody>
          </table>
        ) : (
          <div className="card-body">
            <div className="view-empty">
              <ClipboardCheck size={28} />
              <p>
                {loaded
                  ? loadErr
                    ? "Evalset unavailable — is the control-plane running?"
                    : "No scenarios in the evalset."
                  : "Loading evalset…"}
              </p>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
