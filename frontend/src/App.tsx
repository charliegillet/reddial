import { useEffect, useState } from "react";
import { api, type Attack, type Summary } from "./api";

const GRADE_VAR: Record<string, string> = {
  A: "--grade-a", B: "--grade-b", C: "--grade-c", D: "--grade-d", F: "--grade-f",
};

function pct(x: number | undefined): string {
  return `${Math.round((x ?? 0) * 100)}%`;
}

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
    setRunning(true); setErr(null);
    try {
      const { summary } = await api.runScan(n, 4);
      setSummary(summary);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  const grade = summary?.max_grade ?? "—";
  const gradeColor = `var(${GRADE_VAR[grade] ?? "--ink-faint"})`;
  const vectors = summary
    ? Object.entries(summary.by_vector).sort((a, b) => b[1].leak_rate - a[1].leak_rate)
    : [];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="dot" />
          <h1>RedDial</h1>
          <span className="tag">voice-agent threat console</span>
        </div>
        <span className="spacer" />
        <div className="health">
          <span className={`led ${health === "up" ? "up" : health === "down" ? "down" : ""}`} />
          {health === "up" ? `API online · v${version}` : health === "down" ? "API offline" : "connecting…"}
        </div>
      </header>

      <div className="safety">
        ⚠ ALL DATA IS FAKE — Stripe test BIN (4539…) &amp; specimen SSN. Offline loopback against a mock
        we own. No real PII, no live dialing from this console. Authorized red-teaming only.
      </div>

      <div className="grid">
        {/* ── control column ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <section className="panel">
            <h2>Run scan</h2>
            <div className="field">
              <label htmlFor="n">attack calls (loopback)</label>
              <input id="n" type="number" min={1} max={500} value={n}
                onChange={(e) => setN(Math.max(1, Math.min(500, Number(e.target.value) || 1)))} />
            </div>
            <button className="run-btn" onClick={runScan} disabled={running}>
              {running ? "running campaign…" : "▶ launch campaign"}
            </button>
            {err && <div className="err">! {err}</div>}
            <p className="note">
              Drives the deterministic attacker FSM ↔ vulnerable mock ↔ Luhn classifier. Results are a
              loopback scorecard, not proof against a real agent.
            </p>
          </section>

          <section className="panel">
            <h2>Attack library · {attacks.length}</h2>
            <div>
              {attacks.length === 0 && <div className="empty">no attacks loaded</div>}
              {attacks.map((a) => (
                <div className="atk" key={a.id}>
                  <div><span className="id">{a.id}</span> <span className="cat">{a.category}</span></div>
                  <div className="line">“{a.spoken_template}”</div>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* ── scorecard column ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }} className="stagger">
          <section className="panel">
            <h2>Vulnerability scorecard</h2>
            {!summary ? (
              <div className="empty">No campaign yet — launch one to generate a scorecard.</div>
            ) : (
              <>
                <div className="hero">
                  <div className="grade" style={{ color: gradeColor }}>{grade}</div>
                  <div>
                    <div className="stat-row">
                      <div className="stat"><div className="v" style={{ color: gradeColor }}>{summary.max_score}</div><div className="k">vuln score</div></div>
                      <div className="stat"><div className={`v ${summary.breach_rate > 0 ? "alert" : ""}`}>{pct(summary.breach_rate)}</div><div className="k">breach rate</div></div>
                      <div className="stat"><div className="v">{pct(summary.leak_rate)}</div><div className="k">leak rate</div></div>
                      <div className="stat"><div className="v">{summary.median_time_to_leak_s ?? "—"}s</div><div className="k">median time-to-leak</div></div>
                    </div>
                    <div className="chips">
                      <span className="chip">{summary.total_calls} calls</span>
                      {(summary.failed_calls ?? 0) > 0 && <span className="chip">{summary.failed_calls} failed</span>}
                      {summary.distinct_fields_leaked.map((f) => (
                        <span className={`chip ${f === "card" ? "hot" : ""}`} key={f}>{f}</span>
                      ))}
                    </div>
                  </div>
                </div>
                {summary.time_note && <div className="note">⏱ {summary.time_note}</div>}
              </>
            )}
          </section>

          {summary && vectors.length > 0 && (
            <section className="panel">
              <h2>Per-vector breakdown</h2>
              <table className="vectors">
                <thead>
                  <tr><th>vector</th><th>landed</th><th style={{ width: "40%" }}>leak rate</th><th>breaches</th></tr>
                </thead>
                <tbody>
                  {vectors.map(([id, v]) => {
                    const p = Math.round(v.leak_rate * 100);
                    const col = v.leak_rate >= 0.5 ? "var(--red)" : v.leak_rate > 0 ? "var(--amber)" : "var(--line-bright)";
                    return (
                      <tr key={id}>
                        <td className="id">{id}</td>
                        <td className="num">{v.leaks}/{v.runs}</td>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <div className="bar"><span style={{ width: `${p}%`, background: col }} /></div>
                            <span className="num" style={{ width: 38 }}>{p}%</span>
                          </div>
                        </td>
                        <td className="num">{v.breaches}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>
          )}

          {summary && summary.evidence_samples.length > 0 && (
            <section className="panel">
              <h2>Breach evidence</h2>
              {summary.evidence_samples.map((s, i) => (
                <div className="evidence" key={i}>
                  <div className="head">
                    <span className="badge-breach">BREACH</span>
                    <span className="meta">{s.attack_id} · {s.fields.join(", ") || "—"} · {s.turns_to_first_leak ?? "—"} turns</span>
                  </div>
                  <pre>{s.evidence_span}</pre>
                </div>
              ))}
            </section>
          )}
        </div>
      </div>

      <div className="foot">
        RedDial · autonomous voice red-team · offline harness · all data synthetic ·{" "}
        <a href="https://github.com/nihalnihalani/reddial">github.com/nihalnihalani/reddial</a>
      </div>
    </div>
  );
}
