import { defineConfig } from "vitest/config";

// Pure-function tests: the default jsdom environment is neither installed nor needed.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
