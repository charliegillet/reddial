// Thin typed client for the RedDial control-plane API.
// In dev, Vite proxies /api -> the FastAPI server (see vite.config.ts).
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export interface Attack {
  id: string;
  category: string;
  spoken_template: string;
  success_condition: string;
}

export interface VectorStat {
  runs: number;
  leaks: number;
  breaches: number;
  fields: string[];
  leak_rate: number;
}

export interface EvidenceSample {
  attack_id: string;
  fields: string[];
  evidence_span: string;
  seconds_to_first_leak: number | null;
  turns_to_first_leak: number | null;
}

export interface Summary {
  total_calls: number;
  leak_rate: number;
  breach_rate: number;
  median_time_to_leak_s: number | null;
  max_score: number;
  max_grade: string;
  distinct_fields_leaked: string[];
  by_vector: Record<string, VectorStat>;
  evidence_samples: EvidenceSample[];
  failed_calls?: number;
  run_id?: string;
  time_note?: string;
}

// Lightweight in-process metrics (Settings/Analytics header).
export interface Metrics {
  scans_run: number;
  last_breach_rate: number;
  last_run_id: string | null;
}

// Compact run-history row for the Analytics view (most recent first).
export interface RunSummary {
  run_id: string | null;
  total_calls: number;
  leak_rate: number;
  breach_rate: number;
  max_grade: string;
  max_score: number;
  failed_calls: number;
}

// One conversation turn in a captured loopback transcript.
export interface TranscriptTurn {
  role: string;
  text: string;
  state?: string;
}

// Representative breaching transcript for a run (attacker/target turns).
export interface Transcript {
  run_id: string | null;
  attack_id: string;
  breach: boolean;
  transcript: TranscriptTurn[];
}

// ── Auto-improve loop (iterative eval-driven guardrail hardening) ──
// One round of the loop. `summary` reuses the existing Summary scorecard shape.
export interface RoundRecord {
  round: number;
  clause_added: string | null;   // clause id (e.g. "reject_authority_pretext"); null on baseline
  guardrail_clauses: string[];
  summary: Summary;
  vectors_blocked: string[];
  vectors_newly_blocked: string[];
  vectors_still_breaching: string[];
}

// Per-round metric series for the improvement curve (parallel arrays).
export interface AutoImproveCurve {
  rounds: number[];
  breach_rate: number[];
  leak_rate: number[];
  max_score: number[];
}

interface AutoImproveEndpoint {
  breach_rate: number;
  leak_rate: number;
  max_score: number;
  max_grade: string;
}

// The locked result dict returned by POST /auto-improve and GET /auto-improve/latest.
export interface AutoImproveResult {
  run_id: string;
  rounds: number;
  n_per_round: number;
  seed: number;
  trajectory: RoundRecord[];
  curve: AutoImproveCurve;
  start: AutoImproveEndpoint;
  final: AutoImproveEndpoint;
  improvement: {
    breach_rate_delta: number;
    max_score_delta: number;
    rounds_to_converge: number;
    converged: boolean;
  };
  final_guardrail: string[];
  held_out: { vector: string; breach_before: boolean; breach_after: boolean };
  converged_reason: string;
  honest_note: string;
  time_note: string;
}

async function get<T>(path: string): Promise<T> {
  // One automatic retry: transient network blips on read-only GETs are safe to
  // re-attempt and recover the common "server still booting" race on load.
  let lastErr: unknown;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const r = await fetchWithTimeout(`${BASE}${path}`);
      if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`);
      return (await r.json()) as T;
    } catch (e) {
      lastErr = e;
      // Don't retry HTTP errors (4xx/5xx are deterministic); only retry
      // network/timeout failures, and only once.
      const isNetwork =
        e instanceof TypeError || (e instanceof DOMException && e.name === "AbortError");
      if (!isNetwork || attempt === 1) break;
    }
  }
  throw describeFetchError(path, lastErr);
}

export const api = {
  health: () => get<{ status: string; version: string }>("/healthz"),
  attacks: () => get<{ attacks: Attack[] }>("/attacks"),
  scorecardLatest: () => get<Summary>("/scorecard/latest"),
  metrics: () => get<Metrics>("/metrics"),
  scans: () => get<{ runs: RunSummary[] }>("/scans"),
  // Representative breaching transcript: a specific run's, or the latest run's.
  transcript: (runId?: string) =>
    get<Transcript>(runId ? `/scans/${runId}/transcript` : "/transcript/latest"),
  runScan: async (n: number, concurrency = 1): Promise<{ run_id: string; summary: Summary }> => {
    // A scan runs the attacker FSM N times server-side, so it can take a while;
    // give it a generous timeout (not retried — POST is not idempotent here).
    try {
      const r = await fetchWithTimeout(
        `${BASE}/scans`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ n, concurrency, persist: false }),
        },
        120_000,
      );
      if (!r.ok) throw new Error(`/scans → HTTP ${r.status}`);
      return r.json();
    } catch (e) {
      throw describeFetchError("/scans", e);
    }
  },
  // Latest auto-improve result (in-process, disk-fallback). 404 -> throws.
  autoImproveLatest: () => get<AutoImproveResult>("/auto-improve/latest"),
  // Run the OFFLINE iterative auto-improve loop (forces mock + loopback).
  runAutoImprove: async (
    rounds = 5,
    nPerRound = 24,
    seed = 0,
  ): Promise<AutoImproveResult> => {
    const r = await fetch(`${BASE}/auto-improve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rounds, n_per_round: nPerRound, seed }),
    });
    if (!r.ok) throw new Error(`/auto-improve → HTTP ${r.status}`);
    return r.json();
  },
};
