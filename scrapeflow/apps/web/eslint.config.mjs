import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // Dashboard screens load their data from the same-origin BFF inside
      // effects. The rule cannot tell an async fetch apart from a synchronous
      // render loop, so it is disabled here rather than scattering suppressions.
      "react-hooks/set-state-in-effect": "off",
    },
  },
  globalIgnores([".next/**", "node_modules/**", "next-env.d.ts", "coverage/**"]),
]);
