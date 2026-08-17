import path from "path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  esbuild: {
    jsx: "automatic",
  },
  resolve: {
    alias: [
      { find: "@", replacement: path.resolve(__dirname, "renderer/src") },
      // react-syntax-highlighter ships a CJS main that require()s the ESM-only
      // refractor — force the ESM build so vitest (and any jsdom test) can load it.
      {
        find: /^react-syntax-highlighter$/,
        replacement: path.resolve(__dirname, "node_modules/react-syntax-highlighter/dist/esm/index.js"),
      },
    ],
  },
  test: {
    include: ["tests/**/*.{test,spec}.{js,ts,tsx}"],
    exclude: ["**/e2e/**", "**/node_modules/**"],
    environment: "node",
    setupFiles: ["tests/setup.ts"],
  },
});
