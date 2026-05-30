import { useEffect, useState } from "react";
import { MessagesSquare, ShieldAlert, Bot, Phone, Info } from "lucide-react";
import { motion } from "framer-motion";
import { api, type Summary } from "../api";

// The API teammate is adding `api.transcript(runId?)`. We access it defensively
// (like AnalyticsView does for metrics/scans) so this view renders gracefully
// whether or not the method exists at runtime.
type TranscriptTurn = {
  role: "attacker" | "target";
  text: string;
  state?: string;
};

export interface TranscriptResponse {
  run_id?: string | null;
  attack_id?: string | null;
  breach?: boolean;
  // Index (into transcript) of the turn where PII was leaked, if known.
  breach_turn?: number | null;
  transcript: TranscriptTurn[];
}

type MaybeTranscriptApi = {
  transcript?: (runId?: string) => Promise<TranscriptResponse>;
};

interface ConversationViewProps {
  summary: Summary | null;
}

// Build a minimal, readable conversation from evidence samples when no
// transcript endpoint/data is available. We can only reconstruct the leaked
// turn (the attacker's ask + the target's leaking reply), so it's a partial
// view — clearly labelled as derived.
function deriveFromEvidence(summary: Summary | null): TranscriptResponse | null {
  if (!summary) return null;
  const samples = summary.evidence_samples ?? [];
  if (samples.length === 0) return null;

  const first = samples[0];
  const fields = (first.fields ?? []).join(", ") || "sensitive data";
  const turns: TranscriptTurn[] = [
    {
      role: "attacker",
      text: `Attacker vector "${first.attack_id}" pressed the target for ${fields}.`,
      state: "social-engineering",
    },
    {
      role: "target",
      text: first.evidence_span,
      state: "leaked",
    },
  ];
  return {
    run_id: summary.run_id ?? null,
    attack_id: first.attack_id,
    breach: true,
    breach_turn: 1,
    transcript: turns,
  };
}

export function ConversationView({ summary }: ConversationViewProps) {
  const [data, setData] = useState<TranscriptResponse | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const a = api as unknown as MaybeTranscriptApi;

    async function load() {
      if (typeof a.transcript === "function") {
        try {
          const res = await a.transcript(summary?.run_id ?? undefined);
          if (!cancelled && res && (res.transcript?.length ?? 0) > 0) {
            setData(res);
            setLoaded(true);
            return;
          }
        } catch {
          /* fall through to evidence-derived view */
        }
      }
      if (!cancelled) {
        setData(deriveFromEvidence(summary));
        setLoaded(true);
      }
    }

    setLoaded(false);
    load();
    return () => {
      cancelled = true;
    };
  }, [summary]);

  const turns = data?.transcript ?? [];
  const breachTurn = data?.breach_turn ?? null;

  return (
    <motion.div
      initial={{ y: 10 }}
      animate={{ y: 0 }}
      style={{ display: "flex", flexDirection: "column", gap: "24px" }}
    >
      <div className="card">
        <div className="card-header">
          <MessagesSquare size={18} className="brand-icon" />
          <span className="card-title">Attacker ↔ Target Conversation</span>
          {data?.run_id && (
            <span className="evidence-meta" style={{ marginLeft: "auto" }}>
              run {data.run_id}
              {data.attack_id ? ` · ${data.attack_id}` : ""}
            </span>
          )}
        </div>

        <div className="card-body">
          <div className="transcript-note">
            <Info size={14} />
            <span>
              This is the <strong>offline loopback</strong> conversation (text only — no audio).
              Live PSTN audio is not streamed to this console; see DEPLOY.md for live calls.
            </span>
          </div>

          {!loaded ? (
            <div className="view-empty">
              <MessagesSquare size={28} />
              <p>Loading conversation…</p>
            </div>
          ) : turns.length === 0 ? (
            <div className="view-empty">
              <MessagesSquare size={28} />
              <p>
                No conversation captured yet. Launch a campaign from the Threat Console to
                generate an attacker↔target transcript.
              </p>
            </div>
          ) : (
            <div className="transcript-timeline">
              {turns.map((t, i) => {
                const isBreach = breachTurn === i || (t.state ?? "").toLowerCase() === "leaked";
                const isAttacker = t.role === "attacker";
                return (
                  <motion.div
                    key={i}
                    initial={{ y: 6 }}
                    animate={{ y: 0 }}
                    transition={{ duration: 0.25, delay: Math.min(i * 0.05, 0.4) }}
                    className={`transcript-turn ${isAttacker ? "attacker" : "target"} ${
                      isBreach ? "breach" : ""
                    }`}
                  >
                    <div className="transcript-avatar">
                      {isAttacker ? <ShieldAlert size={16} /> : <Bot size={16} />}
                    </div>
                    <div className="transcript-bubble">
                      <div className="transcript-role">
                        {isAttacker ? "Attacker" : "Target"}
                        {t.state && <span className="transcript-state">{t.state}</span>}
                        {isBreach && <span className="transcript-breach-tag">BREACH</span>}
                      </div>
                      <div className="transcript-text">{t.text}</div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <Phone size={16} className="brand-icon" />
          <span className="card-title">Where is the live call?</span>
        </div>
        <div className="card-body">
          <p className="helper-text" style={{ marginTop: 0 }}>
            RedDial runs a deterministic attacker state machine against an in-process mock
            target. The exchange above is that loopback — fully synthetic PII, no dialing.
            Streaming real PSTN audio into this console is intentionally out of scope; the
            live-calling path is documented in DEPLOY.md.
          </p>
        </div>
      </div>
    </motion.div>
  );
}
