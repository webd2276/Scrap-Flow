import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base so the static build works on GitHub Pages project sites and
// from any sub-path, not only at the domain root.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    target: "es2020",
    cssCodeSplit: true,
  },
});
