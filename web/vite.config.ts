import { reactRouter } from "@react-router/dev/vite";
import { defineConfig } from "vite";

const catalogProxy = {
  "/api": {
    target: process.env.WORKBENCH_TEST_API ?? "http://127.0.0.1:8000",
    rewrite: (path: string) => path.replace(/^\/api/, ""),
  },
};

export default defineConfig({
  plugins: [reactRouter()],
  resolve: {
    tsconfigPaths: true,
  },
  server: {
    proxy: catalogProxy,
  },
  preview: {
    proxy: catalogProxy,
  },
});
