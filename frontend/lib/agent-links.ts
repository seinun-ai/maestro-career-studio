/**
 * Where the app sends a user to learn about connected agents: the Agent inbox's
 * empty state and Settings › Agent apps. Pinned against the headings they
 * point at (test_frontend_agent_inbox.py), so renaming a section fails CI
 * instead of breaking a link, and as their one home (test_frontend_agent_words.py).
 */
const REPO = "https://github.com/seinun-ai/maestro-career-studio/blob/main";

export const CONNECT_AGENT_GUIDE_URL = `${REPO}/docs/GETTING_STARTED.md#5-connect-your-ai-assistant-optional`;
/** How to load the Companion into Chrome (Setup's done screen); pinned by test_frontend_setup_flow.py. */
export const COMPANION_GUIDE_URL = `${REPO}/docs/GETTING_STARTED.md#4-the-companion-browser-extension-optional`;
export const JOB_HUNT_SKILL_URL = `${REPO}/docs/skills/README.md`;
export const AGENT_APPLICATIONS_URL = `${REPO}/README.md#going-all-the-way-agent-applications`;
/** Settings › Agent apps (lib/settings-tabs.ts). */
export const CONNECTED_AGENTS_SETTINGS = "/settings?tab=agents";
