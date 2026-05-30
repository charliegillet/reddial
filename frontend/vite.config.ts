import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy: /api -> the control-plane API (override with VITE_API_TARGET).
const API_TARGET = process.env.VITE_API_TARGET || "http://localhost:8080";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
});
