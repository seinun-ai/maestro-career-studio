"use client";

import Editor, { loader } from "@monaco-editor/react";

/** Monaco, served by this app rather than by a CDN.
 *
 * `@monaco-editor/react` defaults to fetching Monaco from cdn.jsdelivr.net at
 * runtime. For a local-first app that is a privacy leak (the CDN sees the user's
 * IP and referrer whenever an editor opens), an offline breakage, and a supply
 * chain hole — ~900 KB of unpinned third-party script running alongside the
 * user's stored API keys. It was also the app's slowest interaction: the first
 * CDN request measured 1145 ms.
 *
 * `scripts/vendor-monaco.mjs` copies the same files into public/monaco/vs at
 * build time, so this is the identical Monaco build, just served locally.
 *
 * Every Monaco call site MUST import from here rather than from the package.
 * loader.config() is global and first-call-wins, so a component that imports the
 * package directly would work fine in isolation and silently reintroduce the CDN
 * whenever it happened to mount first — which is exactly the kind of bug that
 * only shows up in production. Re-exporting Editor makes the safe path the
 * convenient one.
 */
loader.config({ paths: { vs: "/monaco/vs" } });

export default Editor;
export { loader };
