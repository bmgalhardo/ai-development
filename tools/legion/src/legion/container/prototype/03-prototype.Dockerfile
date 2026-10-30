# The toolchain for this project's checks, on top of a base image with git, Python, uv and the coding CLIs.
# Godot itself and its export templates stay in artifacts/ (git-ignored), as on the host.
ARG BASE
FROM ${BASE}

USER root
# fontconfig: Godot fails its import without it. Xvfb and Mesa: the captures need a display and OpenGL.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fontconfig libgl1 libgl1-mesa-dri libglx-mesa0 \
        libx11-6 libxcursor1 libxext6 libxi6 libxinerama1 libxkbcommon0 libxrandr2 libxrender1 \
        xvfb xauth \
    && rm -rf /var/lib/apt/lists/*
# Chromium's system libraries, for the Web build's browser check (engineering.md: Web pages without a browser).
RUN uvx --no-cache playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*
USER worker
