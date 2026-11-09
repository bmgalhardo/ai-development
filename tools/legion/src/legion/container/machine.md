# This machine

A worker container (Legion's, `tools/legion/` in the workflow repo). The defaults are in `engineering.md`.

- Debian, with git, Python 3, uv (`/usr/local/bin/uv`), Node and npm. A project's image may add its own tools.
- No root and no `sudo`: you can't install system packages. Use uv or npm for anything else.
- The host's local CAs are trusted, so internal HTTPS verifies. Never turn TLS verification off.
- The home, `/home/worker`, is temporary: it is gone when the session ends.
- Memory is limited, by default to 1.5 GB. Keep builds and test runs lean.
- No display. Run a command that needs one under `xvfb-run -a` when the project's image provides it.
- The workflow repo is read-only. Only the project and its `.scratch/<project>/` can be written, and only by an implementer.
