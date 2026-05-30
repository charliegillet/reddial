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

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`);
  return r.json() as Promise<T>;
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
    const r = await fetch(`${BASE}/scans`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ n, concurrency, persist: false }),
    });
    if (!r.ok) throw new Error(`/scans → HTTP ${r.status}`);
    return r.json();
  },
};
