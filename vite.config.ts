import { defineConfig } from "vite";
export default defineConfig({
  base: "./",
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        headers: { Origin: "http://127.0.0.1:8765" },
      },
    },
  },
});
