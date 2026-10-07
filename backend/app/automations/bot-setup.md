# Set up an always-on copy of Maestro Career Studio

You run on a machine that stays on. Install Maestro Career Studio here as the always-on copy of my laptop's Maestro, pair it with my laptop, and keep it running. Do as much as you can yourself. Ask me only for what you can't find, and stop before anything that needs a password or a key typed into chat.

Read these first, from https://github.com/seinun-ai/maestro-career-studio: docs/native-install.md and docs/sync-setup.md ("HTTPS through Funnel").

1. **Install.** Clone the repository and check out the newest release tag (vX.Y.Z), so you match my laptop's version. Set MAESTRO_HOME=$HOME/maestro and run backend/scripts/native/setup.sh. Use a fresh install; don't copy my laptop's database here.
2. **Keep it running.** Add the watchdog cron lines from native-install.md. Let the watchdog start the backend. Never run start.sh from inside one of your own tool calls: your sandbox can stop it when the call ends. To restart: stop.sh --no-pause, wait for the watchdog (up to 5 minutes), then check that /health answers 200.
3. **Point it at my laptop.** In $MAESTRO_HOME/maestro.env (never the repository's .env), set SYNC_REMOTE_URL={laptop_url}. If your only way out is a proxy (HTTPS_PROXY is set in your environment), also put HTTPS_PROXY, NO_PROXY=127.0.0.1,localhost and SSL_CERT_FILE (a CA bundle that trusts the proxy, copied somewhere that survives a reboot) in maestro.env: a watchdog restart has no shell environment. Never put a key in this file. Restart as in step 2.
4. **Check the route.** curl -s -o /dev/null -w '%{http_code}\n' {laptop_url}/api/sync/hello should print 404 with an empty body. That empty 404 is right: the laptop is reachable and refused an unsealed request. If it can't connect, tell me.
5. **Pair.** Tell me you're ready. I'll show a pairing code in Maestro on my laptop (Settings › Connected agents › Second copy); it works once, for 10 minutes. Run: printf '%s\n' '<code>' | "$REPO/backend/scripts/native/sync.sh" --pair --code -   (stdin keeps the code out of the process list). If the first round lists what it would replace, send me the list and wait for my yes before running sync.sh --pair --accept-profile-overwrite.
6. **Sync on a schedule.** Add the sync cron line from sync-setup.md ("Cron lines"). Ask me whether to limit it to my waking hours, and in which time zone.
7. **Connect yourself.** Register Maestro's MCP server as native-install.md "Connect an agent" says. Start it for a run and stop it afterward.
8. **Report back:** the commit you're on, /health/memory, the first sync.sh output and exit code, and your crontab.

Rules:

- Don't join this machine to my tailnet and don't open an SSH tunnel unless I ask. The HTTPS route needs neither.
- The first rounds after pairing can take 20 minutes or more: they move every older job with its files. Let a round finish. Never restart the backend to clear it. One round at a time.
- Never open, print or send the sync key, a used pairing code, the AI key or the job-site password.
