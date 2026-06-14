import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend runs on :8000. In dev we proxy /api -> backend so the frontend can
// use same-origin requests. Override with VITE_API_BASE for non-proxied setups.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Dev proxy: frontend calls /api/* -> backend at :8000 (CORS-free, same-origin).
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
