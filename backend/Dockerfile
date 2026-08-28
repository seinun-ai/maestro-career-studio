FROM python:3.12-slim

# Minimal TeX Live: scheme-basic + exactly the packages the bundled templates
# use (grep usepackage over app/templates/**.tex.j2 before changing this list).
# Replaces 2.91GB of Debian texlive metapackages. pdflatex stays genuine
# pdfTeX — the \pdfinterwordspaceon extraction-fidelity fix is a pdfTeX
# primitive, so do NOT swap the engine for XeTeX/Tectonic without re-running
# the parse certification.
# mirror.ctan.org resolves to a DIFFERENT random CTAN mirror on each request,
# and mirrors go stale or fall mid-sync. A single bad draw used to fail the
# build with a bare `exit code 5` and no explanation — the first command a new
# user runs, so the retries below are the difference between "worked" and an
# opaque error on first contact. Each attempt re-resolves, so a retry lands on
# a different mirror; nothing here masks a genuine, repeatable failure.
RUN set -eux; \
    apt-get update && apt-get install -y --no-install-recommends \
        wget perl ca-certificates fontconfig build-essential; \
    rm -rf /var/lib/apt/lists/*; \
    printf 'selected_scheme scheme-basic\ntlpdbopt_install_docfiles 0\ntlpdbopt_install_srcfiles 0\nTEXDIR /opt/texlive\nTEXMFLOCAL /opt/texlive/texmf-local\nTEXMFSYSVAR /opt/texlive/texmf-var\nTEXMFSYSCONFIG /opt/texlive/texmf-config\n' > /tmp/texlive.profile; \
    ok=""; \
    for attempt in 1 2 3; do \
        echo "TeX Live install attempt ${attempt}/3"; \
        rm -rf /tmp/install-tl /tmp/install-tl.tar.gz /opt/texlive; \
        if wget -qO /tmp/install-tl.tar.gz https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz \
           && mkdir /tmp/install-tl \
           && tar xzf /tmp/install-tl.tar.gz -C /tmp/install-tl --strip-components=1 \
           && /tmp/install-tl/install-tl --profile=/tmp/texlive.profile \
           && /opt/texlive/bin/*/tlmgr install \
                tools graphics babel babel-english hyperref geometry fancyhdr \
                xcharter fontawesome5 enumitem titlesec preprint marvosym cm-super \
                xkeyval xstring fontaxes \
                carlito fira helvetic; \
        then ok="yes"; break; fi; \
        echo "attempt ${attempt} failed (likely a bad or mid-sync CTAN mirror); retrying"; \
        sleep 5; \
    done; \
    if [ -z "$ok" ]; then \
        echo "TeX Live install failed three times against three different CTAN mirrors."; \
        echo "That is no longer mirror luck — check network access to mirror.ctan.org,"; \
        echo "or pin a specific mirror by editing this Dockerfile."; \
        exit 1; \
    fi; \
    ln -s /opt/texlive/bin/* /opt/texlive/texbin; \
    rm -rf /tmp/install-tl /tmp/install-tl.tar.gz /tmp/texlive.profile; \
    pdflatex --version | head -1

ENV PATH="/opt/texlive/texbin:$PATH"

# Run as a normal user, not root. This container bind-mounts the host's
# base_resumes/, applications/, settings/, exports/ and logs/ — every directory
# holding personal data — so root here means root-owned writes on the host and
# turns any code-execution bug in the backend into host filesystem access.
#
# The uid MUST match the host user that owns those directories or the mounts are
# unwritable ON LINUX. 1000 is the usual first user; override when yours differs:
#   docker compose build --build-arg APP_UID=$(id -u) --build-arg APP_GID=$(id -g)
# macOS and Windows Docker Desktop translate ownership for you, so leave the
# defaults alone there — verified 2026-08-04: a default-built image writes every
# bind-mounted data directory and renders a PDF as uid 1000 on macOS.
ARG APP_UID=1000
ARG APP_GID=1000
# `getent ||` because the gid may already belong to a Debian system group and
# `groupadd` then exits 4 with no explanation. macOS users hit this every time:
# the natural `--build-arg APP_GID=$(id -g)` is 20, which is `dialout` here.
# Only the NUMBER matters for file ownership, so joining the existing group is
# the correct outcome, not a workaround.
RUN { getent group $APP_GID >/dev/null || groupadd --gid $APP_GID app; } \
    && useradd --uid $APP_UID --gid $APP_GID --create-home --shell /bin/bash app

WORKDIR /app
# Dependencies come from the hash-pinned lockfile, not from resolving
# pyproject.toml's floors at build time: a published image must be reproducible,
# and a compromised upstream release must not be able to land in it silently.
# pyproject.toml keeps its `>=` floors for editable/dev installs (`pip install
# -e ".[mcp]"` still resolves normally). Regenerate the lock on the target
# platform after changing a dependency:
#   docker run --rm -v "$PWD/backend:/w" -w /w python:3.12-slim \
#     sh -c "pip install pip-tools && pip-compile --extra dev --extra mcp \
#            --generate-hashes --output-file requirements.lock pyproject.toml"
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
    && pip install --no-cache-dir --no-deps -e ".[dev]"

COPY . .
# Numeric, not `app:app`: when APP_GID matched an existing system group above,
# the user's primary group is THAT group and no group named `app` exists.
RUN chown -R $APP_UID:$APP_GID /app
USER app

# Version identity, last so it invalidates one layer and not the TeX Live
# install above. "dev" is what a local `docker compose build` gets, and the
# frontend treats it as "unknown, do not compare".
ARG APP_VERSION=dev
ARG APP_GIT_SHA=""
ENV APP_VERSION=${APP_VERSION}
ENV APP_GIT_SHA=${APP_GIT_SHA}

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
# No --reload: this is the production image. Hot reload is a dev concern and
# docker-compose.dev.yml overrides the command for it. Shipping --reload here
# spawns a file-watching reloader in production and reloads on any bind-mounted
# change, which is exactly the dev/prod confusion the compose split removed.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
