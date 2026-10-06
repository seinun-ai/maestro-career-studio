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

## The worked example

An always-on agent app runs your agent on a small virtual machine. The VM has a
cron-based watchdog, a secret vault, and an outgoing SSH connection to your
laptop over a private network. Your agent drives Maestro through its MCP tools,
as in [native-install.md](native-install.md). The steps below use that VM. Any
machine that can make an outgoing SSH connection to your laptop works the same
way.

The laptop needs Docker and a running Maestro. The VM needs a native install.
**Both must run the same Maestro version.**

## 1. The laptop

1. **Join a private network.** Use one that gives each machine a stable name,
   such as Tailscale. Join the laptop and the VM to it. Never open the laptop to
   the public internet.
2. **Turn on Remote Login** (macOS: System Settings › General › Sharing).
3. **On the VM, make a key just for this.** Keep the private half on the VM
   (mode 0600, passphrase-free so cron can use it):
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
5. **Make the sync key**, once, from your Maestro folder. On a Docker laptop:
   ```bash
   docker compose exec backend python -m scripts.sync_key create
   docker compose exec backend python -m scripts.sync_key show
   ```
   On a native laptop, run these from the repository's `backend/` folder, with
   the venv's Python and the key path set:
   ```bash
   SYNC_KEY_FILE="$MAESTRO_HOME/sync-key" "$MAESTRO_HOME/venv/bin/python" -m scripts.sync_key create
   SYNC_KEY_FILE="$MAESTRO_HOME/sync-key" "$MAESTRO_HOME/venv/bin/python" -m scripts.sync_key show
   ```
   `create` prints only the file's path. `show` prints the key: copy it into
   your vault from your own terminal, once. Never paste it into a chat or a
   ticket. Maestro reads the key file on each request, so a running laptop
   needs no restart. The one exception is a native backend started before
   `start.sh` always set `SYNC_KEY_FILE`: restart that one once
   (`stop.sh --no-pause && start.sh`). The laptop is now the home copy. Its
   sync endpoints answer only requests that carry this key.

## 2. The always-on copy

1. **Install Maestro natively** by following [native-install.md](native-install.md).
2. **Put the vault's key in a file.** Write it straight from the vault's command
   line tool, so it never appears in your shell history:
   ```bash
   ( umask 077; your-vault-command-that-prints-the-key > "$MAESTRO_HOME/sync-key" )
   chmod 600 "$MAESTRO_HOME/sync-key"
   ```
   **Never run `sync_key create` on this machine.** A second key would not
   match the laptop's.
3. **Tell Maestro where the laptop is.** In `$MAESTRO_HOME/maestro.env`, set:
   ```bash
   SYNC_REMOTE_URL=http://127.0.0.1:8101
   ```
   Do not put the key in this file. The address must be this machine's own
   tunnel (`127.0.0.1`, `localhost` or `::1`). Maestro refuses any other address,
   and it ignores `HTTP_PROXY` and the like for this connection, because the key
   and your profile travel in it.
4. **Restart,** because the backend reads `maestro.env` at start:
   ```bash
   "$REPO/backend/scripts/native/stop.sh" --no-pause && "$REPO/backend/scripts/native/start.sh"
   ```
5. **Add the laptop to `~/.ssh/config`** (use your private network's name):
   ```
   Host laptop
       HostName your-laptop.your-network.example
       User your-mac-username
       IdentityFile ~/.ssh/maestro-sync
       BatchMode yes
   ```
6. **Trust the laptop's host key, once.** `BatchMode yes` refuses to ask, so
   the first tunnel would fail with "Host key verification failed." Accept the
   key once, by hand:
   ```bash
   ssh -o StrictHostKeyChecking=accept-new laptop true
   ```
   When you can, compare the fingerprint it shows with the one on the laptop:
   `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. The command ends at once with
   status 1, because the key's forced command is `/usr/bin/false`. That is fine.
7. **Open the tunnel.** It makes the VM's `127.0.0.1:8101` reach the laptop's
   `127.0.0.1:8001`:
   ```bash
   ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
       -L 127.0.0.1:8101:127.0.0.1:8001 laptop
   ```
   It drops when the laptop sleeps. The watchdog below opens it again.
   To check it, run `curl -s http://127.0.0.1:8101/health` on the VM.

To check that sync is on at the laptop, run this on the VM with the tunnel up:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8101/api/sync/hello
```

`401` means the laptop has a key and wants it. `404` means the laptop has no
key yet (step 1.5).

## 3. Cron lines

On the VM, add these to the crontab. They sit next to the backend watchdog from
[native-install.md](native-install.md). Change the paths to yours.

```cron
MAESTRO_HOME=/home/agent/maestro
# keep the backend up (from native-install.md)
*/5 * * * * /home/agent/maestro-career-studio/backend/scripts/native/health.sh >/dev/null 2>&1 || /home/agent/maestro-career-studio/backend/scripts/native/start.sh --watchdog >/dev/null 2>&1
@reboot /home/agent/maestro-career-studio/backend/scripts/native/start.sh --watchdog >/dev/null 2>&1
# keep the tunnel up; the ^ anchor stops pgrep from matching cron's own "sh -c" line
*/5 * * * * pgrep -f '^ssh .*127.0.0.1:8101:127.0.0.1:8001' >/dev/null || nohup ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -L 127.0.0.1:8101:127.0.0.1:8001 laptop >/dev/null 2>&1 &
@reboot nohup ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -L 127.0.0.1:8101:127.0.0.1:8001 laptop >/dev/null 2>&1 &
# one sync round every five minutes
*/5 * * * * /home/agent/maestro-career-studio/backend/scripts/native/sync.sh >/dev/null 2>&1
```

When the laptop does not answer, Maestro waits longer between tries: 5, 10, 20,
then 30 minutes. The first success resets it. A cron line never forces a round.

To run a round by hand without waiting out a backoff, run
`"$REPO/backend/scripts/native/sync.sh" --now`. It forces the round without
pairing. It still honours the 30-second pause after another round: inside it,
the answer is "Synced moments ago."

## 4. First pairing

Do this once, at the keyboard, with the tunnel up:

```bash
"$REPO/backend/scripts/native/sync.sh" --pair
```

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
always-on copy holds stays its own.

## 5. What the marks mean

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

## 6. Full automation and offers

If Full automation is On in Settings, queuing a job on the laptop offers it to
the bot. The job shows "Going to your bot" until the next round. If you do not
press **Keep it here**, the bot takes it and owns it from then on. Only the
laptop offers, only for a job you queue (accepted) there, and only while Full
automation is On. A job you queue while it is Off stays on the laptop, and
switching it Off takes back every offer the bot has not picked up yet. The bot hunts and
applies to its own jobs whether or not the laptop is awake.

## 7. Your agent and `sync_now`

Your agent on the always-on copy can call the MCP tool `sync_now`. It runs one
round now. The job-search brief says `sync.enabled`, and the apply prompts tell
the agent to call `sync_now` at the start and end of a run and to work only on
jobs it owns. A round forced inside the 30 seconds after another one answers
"Synced moments ago." On the laptop, `sync_now` says the bot runs the sync. With
no key, it says "Sync isn't set up."

## 8. Exit codes of `sync.sh`

- **0**: the round worked, or it was skipped for a reason that needs nobody:
  a backoff wait, a busy laptop, an unreachable laptop, or maintenance
  (`stop.sh` pauses it). A round that did not run prints "Sync didn't run: …
  It will try again."
- **1**: a person has to act, or the local backend is down or not set up.
  The message says which, and starts with "Sync failed:" when a person must act.

It never prints the key. Cron discards output in the lines above. Run
`sync.sh` by hand to read the message.

## 9. Backups

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

## 10. Troubleshooting

- **"Update Maestro on both machines to the same version."** The two copies must
  match in version and database revision. The round is skipped and nothing is
  half-done. Update the laptop with `scripts/update.sh`. Update the VM with
  `stop.sh`, `git pull` to the same tag, `setup.sh`, then `start.sh`.
- **"401: Sync key doesn't match."** The VM's key file differs from the laptop's.
  Copy the key from the vault again. Maestro reads the key file on each request,
  so the VM's backend needs no restart. Do not create a new key on the VM.
- **"404: Sync isn't set up on your laptop."** The laptop has no key file. Run
  `sync_key create` there.
- **`sync.sh` says "This copy is not set up as the always-on copy".** The VM
  has no key file, or `SYNC_REMOTE_URL` is unset. Check steps 2.2 to 2.4.
- **"The laptop's address must be this machine's own tunnel (127.0.0.1)."**
  `SYNC_REMOTE_URL` names another host. Set it to the tunnel's address (step 2.3).
- **"Laptop unreachable."** The tunnel is down, or the laptop is asleep or off,
  or Docker is stopped. `sync.sh` prints "Sync didn't run: Laptop unreachable. It will try again." This
  is not an error: Maestro backs off and retries.
  Check the tunnel with `curl -s http://127.0.0.1:8101/health`.
- **A laptop asleep for days.** The bot keeps hunting and applying to its own
  jobs. Mail updates and your queue and skip choices wait as requests. The
  first round after the laptop wakes sends them all. The wait is at most 30
  minutes.
- **"A sync is already running on your laptop."** The laptop answers one round
  at a time. Wait for the next one.
- **"These two copies share one machine id".** The always-on copy was started
  from a copy of the laptop's database. Give it its own data folder from a fresh
  `setup.sh`, then pair again. **A fresh data folder discards everything the
  always-on copy holds on its own: the jobs it owns, their tailored resumes and
  files, and its run log.** Rounds stop on this error, so nothing can be sent to
  your laptop first. Copy out anything you want to keep from the old data folder
  before you replace it.
- **A stuck job.** If the laptop refuses a job five rounds in a row, Maestro
  stops sending it until it changes again. Look at the round's `refused` count.
  Open the job on the machine that owns it and fix or re-save it, and the next
  round tries again.
- **"Work on it here" is refused.** The bot has approved the job or is unsure
  whether a submit went through. Wait for its run to finish and ask again.
