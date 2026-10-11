import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vitest runs without the Tailwind plugin: tests assert behaviour, not CSS.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});