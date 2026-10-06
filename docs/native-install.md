# Run Maestro without Docker on a small always-on machine

This guide installs the Maestro backend straight onto a Linux machine, with no
Docker, and keeps its memory small. It is a pilot: single machine, no sync, no web
app on that machine.

## Who this is for

Use it when a small machine stays on all day and an AI agent works from it. The
agent finds jobs, scores them, tailors resumes and fills applications through
Maestro's MCP server. You do not want Docker or a browser UI on that machine.

If you have a laptop and want the full app, use [GETTING_STARTED.md](GETTING_STARTED.md)
instead.

## Requirements

- Linux (the memory numbers below were measured on arm64).
- Python 3.12 or newer, with the `venv` module.
- About 250 MB of free memory at rest: the backend plus one MCP server. Scoring
  needs a short extra burst, covered under "What the slim settings do".
- Disk for resumes, rendered PDFs and the database, plus about 300 MB for the
  scoring model, which downloads on the first score.
- A clone of this repository. The scripts run from the clone; your data lives
  elsewhere.

## The four commands

All four live in `backend/scripts/native/`. They read `MAESTRO_HOME`, the one
directory that holds your data, the Python environment and the settings file.
It defaults to `~/maestro`.

```bash
export MAESTRO_HOME="$HOME/maestro"
REPO="$HOME/maestro-career-studio"          # your clone

"$REPO/backend/scripts/native/setup.sh"     # install, once; safe to rerun
"$REPO/backend/scripts/native/start.sh"     # start in the background
"$REPO/backend/scripts/native/health.sh"    # print memory; exit 0 when healthy
"$REPO/backend/scripts/native/stop.sh"      # stop, including any helper; pauses the watchdog
```

- **setup** creates `MAESTRO_HOME` (mode 700) with its folders, a Python
  environment in `$MAESTRO_HOME/venv`, and a `maestro.env` file if none exists.
  It installs the backend with the MCP extra, then migrates the database.
  Set `PYTHON` if `python3.12` is not on your PATH. Rerunning keeps your keys.
- **start** refuses to run twice. `start.sh --watchdog` is for supervisors: it
  declines while maintenance is paused (see "Maintenance"). It loads `maestro.env`, starts one backend on
  `127.0.0.1:8001` (change it with `MAESTRO_PORT`), writes `backend.pid`, and
  waits up to 30 seconds for `/health`. Logs go to `$MAESTRO_HOME/logs/backend.log`.
- **stop** sends TERM, waits 10 seconds, then KILL. It succeeds when nothing runs.
  It also pauses the watchdog; `stop.sh --no-pause` stops without that.
- **health** prints the backend's memory as one line of JSON and exits 0. It
  exits 1 when the backend is stopped or unhealthy, and says so when it is
  paused for maintenance.

## What the slim settings do

`start.sh` sets these for you. You do not need to.

- **One worker on 127.0.0.1.** One process is the smallest. Nothing outside the
  machine can reach it.
- **`MALLOC_ARENA_MAX=2`.** Linux's default memory allocator keeps many arenas
  and holds on to freed memory. Two arenas cut resident memory by up to about 10% in our runs.
- **`EMBEDDINGS_OUT_OF_PROCESS=1`.** ATS scoring uses a small language model. Loaded
  inside the backend, it stays in memory for good (about 260 MB). With this
  setting, each score starts a helper process that loads the model, embeds the
  text and exits. Scores are identical either way. The cost is time, not
  accuracy (see the footprint table).
- **At most one helper at a time.** A helper peaks near 290 MB. Two at once
  could run a small machine out of memory, so a lock in
  `app/services/ats/embeddings.py` makes a second score wait.
- **`FASTEMBED_CACHE_PATH=$MAESTRO_HOME/fastembed_cache`.** The model's download
  cache sits on disk. The default is `/tmp`, which is often RAM-backed on a small machine.

## Secrets

- `maestro.env` is mode 0600 and `MAESTRO_HOME` is 700. The scripts re-secure
  both on every run.
- Put keys there from the machine's own secret store (a vault or a secrets
  manager). Never paste a key into a chat, a prompt or a command line.
- No script prints the environment or turns on `set -x`. Install and migration
  output is silenced on purpose, because it can carry authenticated URLs.
- You only need an AI key for features where the backend itself calls a model.
  The commented lines in `maestro.env` list them.
- `maestro.env` is a plain file of shell assignments. Quote any value that has
  spaces or symbols.

## Keep it running

`start.sh` returns as soon as the backend is up, and `health.sh || start.sh --watchdog`
is safe to repeat: `start.sh` refuses when it is already running, and
`--watchdog` makes it wait while you do maintenance. Any supervisor can use that
pair.

### Watchdog cron (works where systemd is unavailable)

```cron
MAESTRO_HOME=/home/agent/maestro
*/5 * * * * /home/agent/maestro-career-studio/backend/scripts/native/health.sh >/dev/null 2>&1 || /home/agent/maestro-career-studio/backend/scripts/native/start.sh --watchdog >/dev/null 2>&1
@reboot /home/agent/maestro-career-studio/backend/scripts/native/start.sh --watchdog >/dev/null 2>&1
```

### systemd (user unit)

Save as `~/.config/systemd/user/maestro.service`. Adjust the paths. This unit
is untested: nobody has run it yet. It is a starting point, so check it on your
machine before you rely on it. The watchdog cron above is the tested option.

```ini
[Unit]
Description=Maestro backend

[Service]
Type=forking
Environment=MAESTRO_HOME=%h/maestro
PIDFile=%h/maestro/backend.pid
ExecStart=%h/maestro-career-studio/backend/scripts/native/start.sh
ExecStop=%h/maestro-career-studio/backend/scripts/native/stop.sh --no-pause
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

systemd is the supervisor here, so the unit does not use `--watchdog`, and its
stop uses `--no-pause` so a reboot does not leave the pause marker behind. For
maintenance, run `systemctl --user stop maestro`, then `systemctl --user start maestro`.

Then `systemctl --user enable --now maestro`. Run `loginctl enable-linger $USER`
once so it starts at boot without a login.

### launchd (macOS)

Save as `~/Library/LaunchAgents/maestro.backend.plist`, then
`launchctl load` it. It checks every five minutes.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>maestro.backend</string>
  <key>EnvironmentVariables</key>
  <dict><key>MAESTRO_HOME</key><string>/Users/agent/maestro</string></dict>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>-c</string>
  <string>R=/Users/agent/maestro-career-studio/backend/scripts/native; $R/health.sh || $R/start.sh --watchdog</string></array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>300</integer>
</dict></plist>
```

### Maintenance: swap the database or update

`stop.sh` pauses the watchdog. It leaves a marker file, `$MAESTRO_HOME/maintenance`
(mode 0600, holding the UTC time), so the next watchdog tick prints that Maestro is
paused and starts nothing. `start.sh` removes the marker and starts, so a manual
start resumes. To swap the database, run `stop.sh`, swap the file, then run
`start.sh`. For a plain restart that should not pause, run
`stop.sh --no-pause && start.sh`. While paused, `health.sh` says so and still
exits 1. A reboot keeps the pause, because the `@reboot` line also uses `--watchdog`.

## Connect an agent

The backend is the only long-running process. The MCP server is started on demand
by the agent's own tooling, talks over stdio, and exits when the run ends.

```bash
BACKEND_URL=http://127.0.0.1:8001 "$MAESTRO_HOME/venv/bin/python" -m mcp_server.server
```

Register that command in the agent's MCP settings, with `BACKEND_URL` in its
environment. Do not leave the MCP server running between runs. One server
costs about 76 MB. The agent should stop it, or let its harness kill it, after each run.

## Read the memory

```bash
curl -s http://127.0.0.1:8001/health/memory
# example: {"rss_mb": 150.3, "peak_mb": 175.0, "platform": "linux"}
```

`rss_mb` is what the backend holds now. `peak_mb` is the highest it has been
since it started. A helper's memory is not in these numbers, because the helper
is a separate process. `health.sh` prints the same line without needing curl.
For the whole machine, also read `free -m` (the "available" column).

## Order of work on a small machine

On a machine near 640 MB, the order of your work matters more than any setting.

- **Score and tailor with the browser closed.** Or keep it under about 130 MB.
  Open it only to browse job sites and fill forms.
- **The numbers.** At rest, the backend is about 130 MB, one MCP server about
  75 MB, and the helper's bookkeeping about 11 MB. A browser adds about 350 MB.
  That is about 565 MB, which fits, but only thinly.
- **A score adds a helper.** It takes about 260-290 MB for 1 to 3 seconds. That
  covers tailoring, quick tailor and creating an application, because each one scores.
- **With the browser open at 350 MB, a score does not fit.** In a test on a
  640 MB box with no swap, every score either got the browser killed or stalled
  the machine for about 60 seconds, then failed. With the browser closed, scores
  took about 1.5 to 2.7 seconds and the box peaked near 560 MB.
- **What failure looks like.** A score fails with `embeddings failed` (HTTP 500)
  in `backend.log`, or the browser is killed. The backend itself survives, and
  the next score works once memory is free.
- **Hunting.** Gather jobs with the browser. Close it. Then save and score the
  batch. Reopen the browser for the next round.
- **Applying.** This already fits. Prepare and tailor a job first, then open the
  browser to fill its form.
- **Skip untailored jobs while applying.** The apply prompt can tailor a job that
  has no PDF yet, and that scores with the browser open. On a small machine,
  skip such a job and leave it for the next tailor batch.

### Run the work in batches

Maestro's automations are already separate prompts, so each can run as its own
batch. Ask your agent to schedule them in sequence, each one finishing before the
next starts. Maestro schedules nothing itself.

| Batch | Browser | What happens |
|---|---|---|
| 1. Job hunt | Open | Browse job sites and collect postings (link and description). |
| 2. Save and score | Closed | Save each job, score it, and file the good ones for you to review. |
| You | — | Queue or skip jobs in the app, or by messaging your agent. |
| 3. Tailor run | Closed | Tailor the queued jobs and make their PDFs. |
| 4. Apply | Open | Fill forms, check the final review, submit. No scoring here. |

The mail check reads your mail through your agent's own connection and scores
nothing, so it can run at any time.

An example hourly rhythm: hunt on the hour, save and score right after it,
tailor at :20, apply at :40. Pick times that leave each batch room to finish.

## Measured footprint

Measured on Linux arm64 (Python 3.12 slim image) with `MALLOC_ARENA_MAX=2`,
five typical cycles of save, score, render, fill and list:

| | Helper on (`start.sh` default) | Helper off |
|---|---|---|
| Backend at startup | about 140-160 MB | about 140-160 MB |
| Backend after scoring | about 157-173 MB | about 408-427 MB |
| One MCP server | about 76 MB | about 76 MB |

- The helper costs about 0.8 seconds per score. The first score takes about 3
  seconds, because the model's files load cold.
- While a score runs, memory rises by about 290 MB for 1 to 3 seconds, then falls.
- Backend plus one MCP server at rest is about 220-250 MB. Leave room for the
  scoring burst and for your agent's browser. See "Order of work on a small machine".

A test pins the backend's memory: `backend/tests/test_memory_budget.py` runs three
typical cycles and fails if the backend ends above 200 MB. It runs on Linux only
and downloads the real model, so it is marked `slow`. Skip it with
`MAESTRO_SKIP_SLOW=1`, which a CI job should set. To measure by hand, run
`python -m scripts.memory_profile --cycles 5` from `backend/`.

## Worked example: an always-on agent app's VM

An app runs an AI agent on its own small virtual machine, around the clock. The
VM has about 640 MB available, no swap, and a browser the agent drives during runs.

1. **Install.** The agent clones the repository, then runs `setup.sh` with
   `MAESTRO_HOME=$HOME/maestro`. If `python3.12` is missing, install it first.
2. **Base resumes.** A fresh install has none. Copy your base resume JSON files
   into `$MAESTRO_HOME/base_resumes/`, then restart with `stop.sh --no-pause` and `start.sh`.
   The backend reads that folder at startup. Each file name, without `.json`,
   becomes the resume's name. Or have the agent create one with the
   `create_base_resume` MCP tool, which needs no restart.
3. **Secrets.** If any key is needed, the agent reads it from the app's secret
   vault and writes it into `maestro.env` with a quoted assignment. The key is never
   typed into a chat or a command line.
4. **Supervision.** User systemd may be unavailable on the VM, so the watchdog
   cron line above does the job. It also restarts the backend after an
   out-of-memory kill. For an update or a database swap, `stop.sh` pauses it and
   `start.sh` resumes (see "Maintenance").
5. **Connect.** The app registers the stdio command above as an MCP server. The
   agent starts it for a run and kills it afterward.
6. **Browser.** Attended applications open the browser on the same machine. It is
   the largest memory user during a run. Follow "Order of work on a small
   machine": tailor with the browser closed, then open it to fill the form.
   Measure it in the pilot report below.

## Pilot report

The agent on the always-on machine fills this in and sends it back.

- [ ] Machine: CPU architecture, total memory, swap (`free -m`), Python version.
- [ ] Free memory before starting: the `available` column of `free -m`.
- [ ] `/health/memory` right after `start.sh`.
- [ ] Run one job hunt. Record `/health/memory` and `free -m` during it and after it.
  Gather jobs with the browser, close it, then save and score the batch.
- [ ] Run one attended apply, with its browser open. Record `/health/memory` and
  `free -m` during the fill and after the browser closes.
- [ ] The time one score took, from the request to the result.
- [ ] Any out-of-memory kill, restart, or watchdog start. Check `dmesg | grep -i oom`
  and `$MAESTRO_HOME/logs/backend.log`. After a watchdog restart, the crash
  traceback is in `backend.log.1`, because `start.sh` keeps the last run's log there.
- [ ] Run `grep 'embeddings failed' $MAESTRO_HOME/logs/backend.log $MAESTRO_HOME/logs/backend.log.1`
  and record how many lines match.
- [ ] Were scores and tailoring run with the browser closed? Note any that were not.
- [ ] Anything that felt slow, or any step that failed.
