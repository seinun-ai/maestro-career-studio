import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Build output, not source: scripts/vendor-monaco.mjs copies the Monaco
    // bundle in here on prebuild/predev so the editor loads from our own
    // origin instead of a CDN. Linting a minified third-party bundle produced
    // ~60 errors that buried every real finding. Nothing here is tracked
    // except .gitkeep.
    "public/**",
  ]),
]);

export default eslintConfig;
