/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The console only talks to the copilot API over HTTP (spec 07). In dev, /api goes to
// `make api` on :8001, which serves the API under /api (spec 08).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8001",
    },
  },
  test: { environment: "jsdom", globals: true },
});
