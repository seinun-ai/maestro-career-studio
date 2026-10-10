# Run an always-on bot

An always-on bot is an agent on a machine that stays on. It works your job
search while your laptop is off. Your laptop keeps your profile. Each job has
one owner.

## What you need

- A machine or an agent app that stays on, can run Python 3.12 and cron, and
  reaches the internet over HTTPS.
- Your laptop, running Maestro, with Tailscale for the HTTPS route.

## Three phases

1. **Install.** [Run Maestro without Docker](native-install.md).
2. **Pair.** [Set up sync](sync-setup.md), over
   [HTTPS through Funnel](sync-setup.md#https-through-funnel) or an
   [SSH tunnel](sync-setup.md#ssh-tunnel).
3. **Run.** Cron keeps the backend up and runs a sync round on a schedule. The
   agent uses Maestro over MCP. The Automations page has the prompts.

## The quick way

In Maestro on your laptop, open Settings › Connected agents › Second copy.
Click **Copy setup prompt** and paste it into your bot. It installs, configures,
and asks you for a pairing code from the same card.

## What we learned

- Start the backend through the watchdog, because an agent's tool call can
  stop `start.sh` when the call ends.
  [Keep it running](native-install.md#keep-it-running).
- Prefer a fresh install: a copied laptop database is replaced or dropped at
  pairing. [The four commands](native-install.md#the-four-commands).
- Let the first pairing round and the first `sync.sh --now` finish. They can
  take 20 minutes or more. Run them in the background and read the log. Don't
  leave them inside a tool call that times out.
  [Pairing](sync-setup.md#pairing).
- An agent restarts with `stop.sh --no-pause` and the watchdog. An update uses
  `start.sh --unpause` after `setup.sh`, then waits for the watchdog.
  [Maintenance](native-install.md#maintenance-swap-the-database-or-update).
- The bot does not join your tailnet and needs no SSH.
  [HTTPS through Funnel](sync-setup.md#https-through-funnel).
- Limit sync to waking hours with `CRON_TZ`, and keep the watchdog lines above
  it. [Cron lines](sync-setup.md#cron-lines).
