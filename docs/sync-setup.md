# Set up a second, always-on copy (sync)

This guide connects your laptop to a second Maestro copy on a machine that stays
on all day. Your agent hunts and applies from that copy while the laptop is
asleep. Nothing here is needed if you run Maestro on one machine. With no sync
key, Maestro behaves exactly as before.

## What sync is

- **The laptop owns the profile.** Base resumes, career history, templates,
  referrals and settings (the AI key and the job-site login included) are
  written on the laptop only. The always-on copy holds a read-only copy and
  gets a fresh one on every round.
- **Each job has one owner.** A job you add on the laptop is the laptop's. A
  job the always-on copy finds is its own. The other machine holds a read-only
  replica, so you can still see it.
- **Nothing merges.** Only the owner writes a job, so two copies never edit the
  same row. A change you want on the other copy's job travels as a request, and
  the owner applies it with Maestro's normal rules.
- **The always-on copy starts every round.** The laptop only answers. Maestro
  runs no scheduler of its own. A cron line (or your agent's `sync_now` tool)
  asks for a round.
- **Never synced:** the Assistant's chats and the Companion's run data.

This guide calls the second machine "the always-on copy" or "your bot".

Both copies must run the same Maestro version. The laptop needs Docker and a
running Maestro. The always-on copy needs a native install
([native-install.md](native-install.md)).

## Sealed messages

Every sync message is encrypted and authenticated with keys derived from the
sync key (AES-256-GCM, HKDF-SHA256). A header MAC is checked before any body
is read. The key never travels.

Anything that is not sealed gets an empty 404, the same response as when sync
is off. On the published name, a response that is not sealed is replaced with
that same empty 404. A replay is refused. That includes a replay after the
laptop restarts: the laptop refuses a seal stamped before it started.

The query string is bound to the seal but not encrypted. A proxy that decrypts
TLS can see job ids and revisions in cursors. It cannot read the message.
[SECURITY.md](../SECURITY.md) and [PRIVACY.md](../PRIVACY.md) say who can see
what.

## Two routes

Both routes pair with the same one-time code. Pick one.

- **HTTPS through Funnel.** For an always-on copy whose only way out is HTTPS
  through a proxy that decrypts TLS. The always-on copy needs no SSH key and
  no Tailscale.
- **SSH tunnel.** For a machine that can open an SSH connection to the laptop.

## HTTPS through Funnel

Funnel publishes only `/api/sync`. While `SYNC_PUBLIC_HOST` is set, every
response on that path is sealed or the bare 404, whatever Host arrives, and
`/api/sync/round` is not a real route through it. You can turn Funnel on before
you show a pairing code. An outsider still gets the empty 404.

### On the laptop

1. In the tailnet admin, turn MagicDNS on and HTTPS certificates on. Add this
   policy line:

   ```json
   "nodeAttrs": [{"target": ["autogroup:member"], "attr": ["funnel"]}]
   ```

2. Publish only the sync path. On macOS the CLI is
   `/Applications/Tailscale.app/Contents/MacOS/Tailscale`. Use that binary in
   place of `tailscale` below.

   ```bash
   tailscale funnel --bg --set-path=/api/sync http://127.0.0.1:8001/api/sync
   ```

   Turn it off with:

   ```bash
   tailscale funnel --https=443 --set-path=/api/sync off
   ```

3. In the laptop's `.env`, set the public name and restart. Docker Compose
   forwards `SYNC_PUBLIC_HOST` to the backend. Set it on the laptop only: on
   the always-on copy it would turn the copy's own sync round into the empty 404.

   ```bash
   SYNC_PUBLIC_HOST=<mac>.<tailnet>.ts.net
   ```

   From the repository root:

   ```bash
   docker compose up -d
   ```

   Write `<mac>.<tailnet>.ts.net`, the machine's MagicDNS name. Do not add a
   path or a port.

### On the always-on copy

1. Install Maestro natively by following [native-install.md](native-install.md).
2. In `$MAESTRO_HOME/maestro.env`, set the laptop's address. No path and no
   query. Do not put the sync key in this file.

   ```bash
   SYNC_REMOTE_URL=https://<mac>.<tailnet>.ts.net
   ```

3. If a proxy on this machine decrypts TLS, set `HTTPS_PROXY`, `NO_PROXY`, and
   `SSL_CERT_FILE` in `$MAESTRO_HOME/maestro.env`. The native scripts load that
   file with `set -a`. A backend the cron watchdog restarts has no shell
   environment, so a proxy variable that exists only in a terminal never
   reaches it. Without `HTTPS_PROXY` and `NO_PROXY` there, the round reports
   "Laptop unreachable" and exits 0, then keeps doing that. `SSL_CERT_FILE` is
   a bundle that contains the proxy's CA. Example values, not a real proxy:
   `HTTPS_PROXY=http://proxy.example:3128` and `NO_PROXY=127.0.0.1,localhost`.
4. Restart, because the backend reads `maestro.env` at start:

   ```bash
   "$REPO/backend/scripts/native/stop.sh" --no-pause && "$REPO/backend/scripts/native/start.sh"
   ```

5. Add the cron lines under [Cron lines](#cron-lines) for this route. This
   machine does not get an SSH key, and it does not join Tailscale.

Then pair, under [Pairing](#pairing).

## SSH tunnel

Keep the tunnel limited to one forward. Pairing still uses the code in
[Pairing](#pairing). There is no separate enrollment that sends the key in the
clear.

### On the laptop

1. **Join a private network.** Use one that gives each machine a stable name,
   such as Tailscale. On the always-on copy, run `tailscale up` and open its
   interactive login link yourself to join the same network as the laptop. Set
   up a tag such as `tag:maestro-bot` in your network's policy, advertise it
   with `tailscale up --advertise-tags=tag:maestro-bot`, and permit that tag to
   reach only the laptop's SSH port. This path needs no auth key or secret
   pasted into a chat. Never open the laptop to the public internet.
2. **Turn on Remote Login** (macOS: System Settings › General › Sharing).
3. **On the always-on copy, make a key just for this.** Keep the private half
   there (mode 0600, passphrase-free so cron can use it):

   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/maestro-sync -N '' -C maestro-bot
   ```

4. **Add one restricted line** to the laptop's `~/.ssh/authorized_keys`, using
   the public half:

   ```
   restrict,port-forwarding,permitopen="127.0.0.1:8001",command="/usr/bin/false" ssh-ed25519 AAAA… maestro-bot
   ```

   Keep `command="/usr/bin/false"`: `restrict` alone still lets the key run a
   shell. With it, this key can open one forward to Maestro's port and do
   nothing else, and port forwarding still works.

### On the always-on copy

1. **Install Maestro natively** by following [native-install.md](native-install.md).
2. **Tell Maestro where the laptop is.** In `$MAESTRO_HOME/maestro.env`, set:

   ```bash
   SYNC_REMOTE_URL=http://127.0.0.1:8101
   ```

   Do not put the key in this file. The address must be this machine's own
   tunnel (`127.0.0.1`, `localhost` or `::1`) or an `https://` address with no
   path and no query. For this tunnel, Maestro ignores `HTTP_PROXY` and the
   like, because the connection stays on the machine.
3. **Restart,** because the backend reads `maestro.env` at start:

   ```bash
   "$REPO/backend/scripts/native/stop.sh" --no-pause && "$REPO/backend/scripts/native/start.sh"
   ```

4. **Add the laptop to `~/.ssh/config`** (use your private network's name):

   ```
   Host laptop
       HostName your-laptop.your-network.example
       User your-mac-username
       IdentityFile ~/.ssh/maestro-sync
       BatchMode yes
   ```

5. **Trust the laptop's host key, once.** `BatchMode yes` refuses to ask, so
   the first tunnel would fail with "Host key verification failed." Accept the
   key once, by hand:

   ```bash
   ssh -o StrictHostKeyChecking=accept-new laptop true
   ```

   When you can, compare the fingerprint it shows with the one on the laptop:
   `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. The command ends at once
   with status 1, because the key's forced command is `/usr/bin/false`. That
   is fine.
6. **Open the tunnel.** It makes this machine's `127.0.0.1:8101` reach the
   laptop's `127.0.0.1:8001`:

   ```bash
   ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
       -L 127.0.0.1:8101:127.0.0.1:8001 laptop
   ```

   It drops when the laptop sleeps. The watchdog below opens it again.
   To check it, run `curl -s http://127.0.0.1:8101/health` on the always-on
   copy.

An unsealed call to `/api/sync/hello` is an empty 404 whether or not the laptop
has a key. Do not use that call to see if sync is on.

Show a pairing code only after this tunnel is up. Then pair, under
[Pairing](#pairing).

## Pairing

Do this once, at the keyboard, with the route up.

On the laptop, open **Settings › Connected agents › Second copy** and click
**Show a pairing code**. The card says "Pair an always-on copy of Maestro with
this laptop." Clicking the button creates the sync key if this laptop does not
have one yet.

The card has these states:

- **Show a pairing code.** The window is closed.
- The code is on screen. It is 16 characters, shown as four groups
  (`XXXX-XXXX-XXXX-XXXX`), with **Copy pairing code**. The card says "Paste
  this code to your bot. It works once, for 10 minutes." A countdown reads
  "Expires in M:SS", and **Stop** is next to it.
- **Show a new pairing code.** A window is still open, but this page does not
  hold the code (a reload drops it). The stored digest is the enroll secret:
  anyone who can read the laptop's database, or a backup taken while the window
  is open, could enroll until it ends. That is why the window is short, single
  use, and Stop exists. A new code replaces the old one. The old code stops
  working.
- **Stop.** The window closes and the code stops working. The key file stays.
- **Paired with your bot at** the local time. Shown after a copy has paired.
  It stays on the card after the window closes.

The code works once, for 10 minutes, with no attempt limit. A wrong try does
not use it up. It is never logged.

On the always-on copy, prefer reading the code from stdin. It never appears
in the process list:

```bash
"$REPO/backend/scripts/native/sync.sh" --pair --code -
```

Type or paste the code and press Enter. `sync.sh --pair --code <code>` also
works, and the code then shows up in the process list.

The script asks its own backend to enroll. The backend writes the key privately
(mode 0600) and returns only success. No key enters the command, the chat, or
the script output. The code is retired as soon as the laptop accepts it, and
the card shows **Paired with your bot at** the local time. The script then runs
the first pairing round. If that round stops, run `sync.sh --pair` again. The
saved key is reused. You do not need a new code.

If the code is expired, already used, or the window was stopped, the script
prints "Pairing didn't work. Show a pairing code on your laptop and try again."
and exits 1. Show a new code and retry.

The first round replaces the always-on copy's profile with the laptop's. If
that would lose something, the round stops and lists what it would lose. It
lists table names and row keys, never values:

- the tables and rows that differ,
- base resumes only the always-on copy has, and the applications that use them,
- jobs both copies hold where the always-on copy already has progress.

Read the list. If you accept it, run:

```bash
"$REPO/backend/scripts/native/sync.sh" --pair --accept-profile-overwrite
```

Accepting means replace, never merge. A fresh install has nothing to lose and
pairs without the flag. Points the always-on copy recorded as "I can't
confirm this" never block pairing, and they are sent to the laptop.

After pairing, a job both copies already hold is the laptop's. A job only the
always-on copy holds stays its own. Jobs that existed before pairing are sent
on the first rounds.

## Cron lines

On the always-on copy, add lines to the crontab. They sit next to the backend
watchdog from [native-install.md](native-install.md). Change the paths to yours.

Both routes use the sync line. The SSH route also keeps the tunnel lines. The
HTTPS route does not.

```cron
MAESTRO_HOME=/home/agent/maestro
# keep the backend up (from native-install.md)
*/5 * * * * /home/agent/maestro-career-studio/backend/scripts/native/health.sh >/dev/null 2>&1 || /home/agent/maestro-career-studio/backend/scripts/native/start.sh --watchdog >/dev/null 2>&1
@reboot /home/agent/maestro-career-studio/backend/scripts/native/start.sh --watchdog >/dev/null 2>&1
# one sync round every five minutes
*/5 * * * * /home/agent/maestro-career-studio/backend/scripts/native/sync.sh >/dev/null 2>&1
```

SSH tunnel only. The `^` anchor stops `pgrep` from matching cron's own
`sh -c` line:

```cron
*/5 * * * * pgrep -f '^ssh .*127.0.0.1:8101:127.0.0.1:8001' >/dev/null || nohup ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -L 127.0.0.1:8101:127.0.0.1:8001 laptop >/dev/null 2>&1 &
@reboot nohup ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -L 127.0.0.1:8101:127.0.0.1:8001 laptop >/dev/null 2>&1 &
```

When the laptop does not answer, Maestro waits longer between tries: 5, 10, 20,
then 30 minutes. The first success resets it. A cron line never forces a round.

To run a round by hand without waiting out a backoff, run
`"$REPO/backend/scripts/native/sync.sh" --now`. It forces the round without
pairing. It still honours the 30-second pause after another round: inside it,
the answer is "Synced moments ago."

## What the marks mean

On the laptop's web app, each job shows who owns it.

- **With your bot.** The always-on copy owns this job. You can read it. To
  change it you ask the bot. The button **Work on it here** asks for it back.
  The bot returns it at the next round, unless it is applying right now.
  Then you see "Your bot is applying to this one; try again after its run."
- **On your laptop.** What the bot's copy shows for a job the laptop owns. Your
  agent sees it as the job's `ownership`.
- **Going to your bot.** You queued this job with full automation on, and it
  will go to the bot at the next round. **Keep it here** cancels that.
- **Sent at the next sync.** You queued, skipped, changed the status of, or
  added a note to a job the other copy owns. The request waits and is applied
  by the owner at the next round. If the rules refuse it (for example, a skip
  on a job already submitted), Recent runs shows it with the reason.

Everything else on the other copy's job is read-only, with a line naming the
owner. This covers tailoring, Q&A, scores and applying. The Assistant, MCP tools
and the Companion follow the same rule.

## Full automation and offers

If Full automation is On in Settings, queuing a job on the laptop offers it to
the bot. The job shows "Going to your bot" until the next round. If you do not
press **Keep it here**, the bot takes it and owns it from then on. Only the
laptop offers, only for a job you queue (accepted) there, and only while Full
automation is On. A job you queue while it is Off stays on the laptop, and
switching it Off takes back every offer the bot has not picked up yet. The bot
hunts and applies to its own jobs whether or not the laptop is awake.

## Your agent and `sync_now`

Your agent on the always-on copy can call the MCP tool `sync_now`. It runs one
round now. The job-search brief says `sync.enabled`, and the apply prompts tell
the agent to call `sync_now` at the start and end of a run and to work only on
jobs it owns. A round forced inside the 30 seconds after another one answers
"Synced moments ago." On the laptop, `sync_now` says the bot runs the sync. With
no key, it says "Sync isn't set up."

## Exit codes of `sync.sh`

- **0**: the round worked, or it was skipped for a reason that needs nobody:
  a backoff wait, a busy laptop, an unreachable laptop, or maintenance
  (`stop.sh` pauses it). A round that did not run prints "Sync didn't run: …
  It will try again."
- **1**: a person has to act, or the local backend is down or not set up.
  The message says which, and starts with "Sync failed:" when a person must act.

It never prints the key. Cron discards output in the lines above. Run
`sync.sh` by hand to read the message.

## Backups

Each machine keeps its own database, and a sync round carries the rest. Back
each one up to a folder your cloud drive already syncs.

- **The always-on copy.** Run [Litestream](https://litestream.io) next to the
  backend. Start it under the same watchdog. A minimal `/etc/litestream.yml`
  (or `~/litestream.yml`):

  ```yaml
  dbs:
    - path: /home/agent/maestro/data/maestro_cs.sqlite3
      replicas:
        - path: /home/agent/synced-folder/maestro-bot
  ```

  Your drive's client or `rclone` carries that folder to the cloud. To rebuild,
  stop Maestro, run `litestream restore -o <database path> /home/agent/synced-folder/maestro-bot`,
  start it, and run `sync.sh`.
- **The laptop.** Maestro's database sits in a folder Docker mounts, and that
  mount does not promise the shared memory a live WAL file needs. Do not run
  Litestream on it. Take an online snapshot instead:

  ```bash
  docker compose exec -T backend python -m app.tools.backup_db --stdout | gzip > ~/synced-folder/maestro-laptop-$(date +%F).sqlite3.gz
  ```

  This is the same snapshot `scripts/update.sh` takes.

Either machine can be rebuilt from its backup plus one sync round.

## Troubleshooting

- **"Update Maestro on both machines to the same version."** The two copies must
  match in version and database revision. The round is skipped and nothing is
  half-done. Update the laptop with `scripts/update.sh`. Update the always-on
  copy with `stop.sh`, `git pull` to the same tag, `setup.sh`, then `start.sh`.
- **"The laptop didn't accept this copy's seal: the key differs, sync is off there, or the laptop has just restarted."**
  The outcome is `needs_person`. The key files differ, or the laptop
  has no key. Do not create a second key on the always-on copy. Right after a
  laptop restart, a clock on the always-on copy that is running behind can
  cause this same refusal for up to 5 minutes. The next round after the clocks
  agree works.
- **"The laptop's answer couldn't be verified."** The outcome is `transient`.
  The script prints "Sync didn't run: … It will try again." and exits 0.
- **"The certificate bundle in SSL_CERT_FILE can't be read."** The outcome is
  `needs_person`. Point `SSL_CERT_FILE` at a bundle file this machine can read,
  containing the proxy's CA, and restart.
- **"The proxy settings in this machine's environment can't be used."** The
  outcome is `needs_person`. Fix `HTTPS_PROXY` or `NO_PROXY` on this machine.
  The message does not include the proxy address.
- **"The laptop's address must be this machine's own tunnel or an https:// address."**
  The outcome is `needs_person`. `SYNC_REMOTE_URL` must be this
  machine's own tunnel (`127.0.0.1`, `localhost` or `::1`) or an `https://`
  address with no path and no query. A public `http://` address is refused.
- **An expired or used code.** The script prints "Pairing didn't work. Show a
  pairing code on your laptop and try again." Show a new code. A code that is
  not 16 characters prints "That pairing code isn't valid."
- **`sync.sh` says "This copy is not set up as the always-on copy".** This
  machine has no key file, or `SYNC_REMOTE_URL` is unset. Check the route
  steps, show a pairing code, and run `sync.sh --pair --code -`.
- **"Laptop unreachable."** The tunnel is down, or the laptop is asleep or off,
  or Docker is stopped. The outcome is `transient`. `sync.sh` prints "Sync
  didn't run: Laptop unreachable. It will try again." This is not an error:
  Maestro backs off and retries. On the SSH route, check the tunnel with
  `curl -s http://127.0.0.1:8101/health`. On the HTTPS route, the same line
  repeating forever means `HTTPS_PROXY` or `NO_PROXY` is missing from
  `maestro.env` (the watchdog restart does not keep your shell).
- **A laptop asleep for days.** The bot keeps hunting and applying to its own
  jobs. Mail updates and your queue and skip choices wait as requests. The
  first round after the laptop wakes sends them all. The wait is at most 30
  minutes.
- **"A sync is already running on your laptop."** The laptop answers one round
  at a time. Wait for the next one.
- **"These two copies share one machine id".** The always-on copy was started
  from a copy of the laptop's database. Give it its own data folder from a
  fresh `setup.sh`, then pair again. **A fresh data folder discards everything
  the always-on copy holds on its own: the jobs it owns, their tailored resumes
  and files, and its run log.** Rounds stop on this error, so nothing can be
  sent to your laptop first. Copy out anything you want to keep from the old
  data folder before you replace it.
- **A stuck job.** If the laptop refuses a job five rounds in a row, Maestro
  stops sending it until it changes again. Look at the round's `refused` count.
  Open the job on the machine that owns it and fix or re-save it, and the next
  round tries again.
- **"Work on it here" is refused.** The bot has approved the job or is unsure
  whether a submit went through. Wait for its run to finish and ask again.
- **The platform that hosts the always-on copy is suspect.** Delete the key
  file on both machines and pair again. On the laptop that is
  `settings/secrets/sync-key`. On the always-on copy it is
  `$MAESTRO_HOME/sync-key`. Show a new pairing code. Prefer `--code -`.
