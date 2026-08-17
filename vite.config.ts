import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import * as path from "path";

export default defineConfig({
  root: path.resolve(__dirname, "renderer"),
  base: "./",
  plugins: [react()],
  build: {
    outDir: "../dist-renderer",
    emptyOutDir: true,
  },
  server: {
    // Bind IPv4 explicitly — macOS localhost often resolves to ::1 only,
    // while scripts/dev.js + Electron probe 127.0.0.1.
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "renderer/src"),
    },
  },
});
