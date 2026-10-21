import { SetupFlow } from "@/components/setup/setup-flow";

/**
 * Setup, the first run (board "Setup in four steps"): AI model, resume, where and what, form answers, then
 * a done screen. A brand-new install lands here once from Today, Today's setup card opens it until the
 * required steps are done, and it works opened directly (Settings' Run setup again).
 */
export default function SetupPage() {
  return <SetupFlow />;
}
