# The worker image: the coding CLIs and a non-root user. See Overmind's README.
FROM debian:trixie-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl git less nodejs npm procps python3 ripgrep \
    && rm -rf /var/lib/apt/lists/*

# The host's own CAs (build.sh passes /usr/local/share/ca-certificates), so internal HTTPS verifies.
COPY --from=host-ca . /usr/local/share/ca-certificates/
RUN update-ca-certificates

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /uvx /usr/local/bin/

# Pinned; bump them deliberately. The CLIs never update themselves in here.
ARG CLAUDE_VERSION=2.1.312
ARG CODEX_VERSION=0.164.0
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_VERSION}" "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force
ENV DISABLE_AUTOUPDATER=1

# The host user's ids, so files written to the mounts belong to them.
ARG UID=1000
ARG GID=1000
RUN groupadd -g "$GID" worker && useradd -m -u "$UID" -g "$GID" -s /bin/bash worker
USER worker
# Codex's login file and both CLIs' session folders are mounted in here; the CLIs write their other files beside them.
RUN mkdir /home/worker/.claude /home/worker/.codex
WORKDIR /home/worker
