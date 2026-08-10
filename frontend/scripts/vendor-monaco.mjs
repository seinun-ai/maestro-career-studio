// Copy Monaco's prebuilt AMD bundle into public/ so the app serves it itself.
//
// Without this, @monaco-editor/react falls back to its default loader path,
// which is a CDN (cdn.jsdelivr.net). That default is wrong for this app in three
// separate ways: it leaks the user's IP and referrer to a third party every time
// an editor opens, it breaks both editors offline, and it executes ~900 KB of
// unpinned third-party script in a process holding the user's API keys. It is
// also slow — the first CDN request measured 1145 ms against 10-30 ms locally.
//
// Vendored rather than bundled on purpose: @monaco-editor/react loads Monaco
// through its own AMD loader, so handing it a local `vs` directory is a one-line
// change, while bundling would mean configuring web workers in the Next build
// for no user-visible gain.
//
// Output is generated and gitignored. `npm run build` and `npm run dev` both
// depend on it via prebuild/predev.

import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "..", "node_modules", "monaco-editor", "min", "vs");
const dest = resolve(here, "..", "public", "monaco", "vs");

if (!existsSync(src)) {
  // Fail loudly. A silent skip would leave loader.config() pointing at a 404,
  // and the editor would simply never appear.
  console.error(
    `[vendor-monaco] ${src} not found. Is monaco-editor installed? ` +
      `It must be a direct dependency, not just a peer of @monaco-editor/react.`,
  );
  process.exit(1);
}

rmSync(dest, { recursive: true, force: true });
cpSync(src, dest, { recursive: true });
console.log(`[vendor-monaco] vendored ${src} -> ${dest}`);
