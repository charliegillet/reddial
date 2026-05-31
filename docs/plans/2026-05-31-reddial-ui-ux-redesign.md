# RedDial UI/UX Redesign Plan

## Aesthetic Direction: Enterprise SOC

### Purpose & Tone
The goal is to transform the current "Cyber Gladiator" dashboard into a high-signal, professional Security Operations Center (SOC) console. It needs to feel authoritative, clean, and highly structured, focusing on data density and clarity without unnecessary noise or "hacker" tropes.

### Visual Language
*   **Colors:** Subdued and high-contrast. 
    *   Background: Deep charcoal/slate (e.g., `#0a0c10`) instead of pure black.
    *   Surfaces: Slightly elevated shades of slate (`#11141a`, `#1c212b`) for cards and panels.
    *   Accents: Semantic colors used sparingly. Crimson (`#e53935`) for breaches/critical alerts, amber (`#fb8c00`) for warnings, and muted blue (`#2979ff`) for active states.
*   **Typography:**
    *   Headers/Body: A premium, highly legible sans-serif font (e.g., `Geist` or `Inter`) to give an enterprise software feel.
    *   Data/Code: A clean monospace font (`JetBrains Mono` or `Fira Code`) reserved strictly for logs, IDs, and raw evidence.
*   **Motion & Effects:** Remove scanlines, film grain, and glowing neon pulses. Use subtle, refined micro-interactions—smooth color transitions on hover, crisp fade-ins for loaded data, and precise progress bar fills.
*   **Spatial Composition:** Highly structured, rigid grid layouts. Generous padding inside cards, but tight alignment between modules.

### Structural Refactoring (`frontend/src/App.tsx`)
The current monolithic `App.tsx` will be broken down into distinct, manageable components to improve maintainability and UX flow:
1.  **`Layout` & `Topbar`:** Fixed header with clear status indicators and breadcrumbs.
2.  **`ControlSidebar`:** A dedicated left-side panel housing the campaign launcher and the attack vector library.
3.  **`ScorecardDashboard` (Main Area):**
    *   **`SummaryMetrics`:** A high-level overview card (Grade, Vuln Score, Breach Rate).
    *   **`VectorPerformanceTable`:** A cleanly formatted data table with inline visual indicators for leak rates.
    *   **`EvidenceLog`:** A structured, terminal-like view for breach transcripts, featuring syntax highlighting or distinct coloring for attacker vs. target dialogue.

### Execution Steps
1.  **Dependencies:** Install `lucide-react` for clean, professional SVG icons.
2.  **CSS Overhaul:** Completely rewrite `styles.css` using a strict CSS variable system for the new Enterprise SOC palette. Remove all background gradients, overlays, and pulse animations.
3.  **Componentization:** Refactor `App.tsx` into smaller functional components (either within the same file or split into a `components/` directory, depending on preference).
4.  **Polish:** Ensure responsive design holds up and that all edge cases (loading states, errors, empty states) look intentional and polished.