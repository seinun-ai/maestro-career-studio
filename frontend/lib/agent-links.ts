/**
 * Where the app sends a user to learn about connected agents. Pinned against
 * the headings they point at (test_frontend_agent_inbox.py), so renaming a
 * README section fails CI instead of breaking a link.
 */
const REPO = "https://github.com/seinun-ai/maestro-career-studio/blob/main";

export const JOB_HUNT_SKILL_URL = `${REPO}/docs/skills/README.md`;
export const AGENT_APPLICATIONS_URL = `${REPO}/README.md#going-all-the-way-agent-applications`;
/** Settings › Connected agents (lib/settings-tabs.ts). */
export const CONNECTED_AGENTS_SETTINGS = "/settings?tab=agents";
