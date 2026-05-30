import { Settings as SettingsIcon, ShieldCheck, BookOpen, Wifi, Tag } from "lucide-react";
import { motion } from "framer-motion";

interface SettingsViewProps {
  apiBase: string;
  version: string;
  health: "up" | "down" | "?";
}

export function SettingsView({ apiBase, version, health }: SettingsViewProps) {
  const rows: { icon: React.ReactNode; label: string; value: string }[] = [
    { icon: <Wifi size={16} />, label: "API Base", value: apiBase },
    { icon: <Tag size={16} />, label: "Version", value: version ? `v${version}` : "unknown" },
    {
      icon: <ShieldCheck size={16} />,
      label: "Control-Plane Status",
      value: health === "up" ? "Online" : health === "down" ? "Offline" : "Connecting…",
    },
  ];

  return (
    <motion.div
      initial={{ y: 10 }}
      animate={{ y: 0 }}
      style={{ display: "flex", flexDirection: "column", gap: "24px" }}
    >
      <div className="card">
        <div className="card-header">
          <SettingsIcon size={18} className="brand-icon" />
          <span className="card-title">Configuration</span>
        </div>
        <div className="card-body">
          <dl className="settings-list">
            {rows.map((r) => (
              <div className="settings-row" key={r.label}>
                <dt className="settings-key">
                  <span className="settings-key-icon">{r.icon}</span>
                  {r.label}
                </dt>
                <dd className="settings-val">{r.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <ShieldCheck size={16} className="brand-icon" />
          <span className="card-title">Safety Posture</span>
        </div>
        <div className="card-body">
          <div className="safety-banner" style={{ marginBottom: 24 }}>
            <div className="banner-icon"><ShieldCheck size={20} /></div>
            <div className="banner-text">
              <p><strong>DIALING DISABLED · OFFLINE HARNESS</strong></p>
              <p>This console never places live calls. All runs execute against a deterministic, in-process loopback target using synthetic PII (Stripe test BINs, specimen SSNs). No third-party calls are made in the scan/data path (the only external request is the Google Fonts stylesheet).</p>
            </div>
          </div>
          <div className="chip-group" style={{ marginTop: 0 }}>
            <span className="chip">no live dialing</span>
            <span className="chip">synthetic PII only</span>
            <span className="chip">offline loopback</span>
            <span className="chip">no telemetry</span>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <BookOpen size={16} className="brand-icon" />
          <span className="card-title">Documentation</span>
        </div>
        <div className="card-body">
          <ul className="doc-links">
            <li>
              <a href="https://github.com/nihalnihalani/reddial/blob/main/docs/DEPLOY.md"
                 target="_blank" rel="noopener noreferrer">Deploy & Operate Guide</a>
            </li>
            <li>
              <a href="https://github.com/nihalnihalani/reddial/blob/main/README.md"
                 target="_blank" rel="noopener noreferrer">Project README</a>
            </li>
          </ul>
        </div>
      </div>
    </motion.div>
  );
}
