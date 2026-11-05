import { defineConfig } from "vite";
import solid from "vite-plugin-solid";
import tailwindcss from "@tailwindcss/vite";

const BACKEND = process.env.ADPLUS_BACKEND ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [solid(), tailwindcss()],
  server: {
    host: "127.0.0.1",   // localhost resolves to ::1 on macOS; keep one address
    port: 5174,
    strictPort: true,
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/ws": { target: BACKEND.replace(/^http/, "ws"), ws: true },
    },
  },
  build: {
    target: "es2022",
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
  },
});
