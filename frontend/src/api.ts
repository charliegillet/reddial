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

// Default per-request timeout. Without this a dead/hung control-plane would
// leave fetches pending forever (permanent "Connecting…"/spinner states).
const DEFAULT_TIMEOUT_MS = 15_000;

// Turn raw network/abort failures into a friendly, consistent message so the
// UI can surface "API offline" rather than a bare `TypeError: Failed to fetch`.
function describeFetchError(path: string, e: unknown): Error {
  if (e instanceof DOMException && e.name === "AbortError") {
    return new Error(`${path} → request timed out`);
  }
  if (e instanceof TypeError) {
    // fetch() rejects with a TypeError when the network is unreachable.
    return new Error(`${path} → control-plane unreachable`);
  }
  return e instanceof Error ? e : new Error(String(e));
}

// fetch() with an AbortController-backed timeout.
async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
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
};
