import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Dev proxy: forward /v1, /admin, /audit, /metrics to gateway
  server: {
    proxy: {
      "/v1": { target: "http://localhost:8000", changeOrigin: true },
      "/admin": { target: "http://localhost:8000", changeOrigin: true },
      "/audit": { target: "http://localhost:8000", changeOrigin: true },
      "/metrics": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
