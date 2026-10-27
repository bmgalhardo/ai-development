# This machine: tools and gotchas

What every project finds on this machine, and how to use it. A project's
engineering doc says which of these it uses, with its own paths and
commands.

## Python

- uv is at `~/.local/bin/uv`. A project's `tools/` may be a uv project:
  `uv sync --project tools` once, then
  `uv run --project tools python tools/<script>.py`.
- If a venv's Python fails to start ("No module named 'encodings'", after a
  Python upgrade), run `uv sync --project tools` again.
- The system Python has no PIL. To read or convert images, use a uv
  venv with pillow: `uv venv ~/.cache/img-venv`, then
  `uv pip install -p ~/.cache/img-venv/bin/python pillow`.
- `/tmp` is small. Put venvs and downloads under `~/.cache/` or the
  scratchpad.

## Shell

- Wait for a long run with `run_in_background`, not `sleep`: a chained
  `sleep` is blocked. Give the run a `timeout` above its expected time.
- `pkill -f <pattern>` kills the shell itself if the pattern appears in
  the command line.

## Worktrees

The Agent tool's `isolation: "worktree"` fails (`.claude` is a symlink).
Use `git -C ../<project> worktree add <scratchpad>/wt-<slug> -b <branch>`.
It has no `artifacts/` (not in git): link the project's `artifacts/` in and
don't commit the link. Issues stay in this repo's `.scratch/<project>/`.
Merge the branch and `git worktree remove` it when done.

## Screenshots and display

- Use `DISPLAY=:0`. If it isn't there, use the private Xvfb on `:77`
  (below). Mesa's software GL is enough for OpenGL captures, such as Godot's.
- **No display (desktop session off, `/tmp/.X11-unix` empty):** run a
  private Xvfb without root. `apt-get download xvfb libunwind8 libxfont2
  libfontenc1 xkb-data x11-xkb-utils xserver-common libxkbfile1`, `dpkg -x`
  each into a scratch `root/`, then start it inside `unshare -r -m`,
  bind-mounting a copy of `/usr/bin` with `xkbcomp` added over `/usr/bin`
  (Xvfb only looks for `/usr/bin/xkbcomp`), with
  `LD_LIBRARY_PATH=root/usr/lib/x86_64-linux-gnu` and `Xvfb :77 -screen 0
  1280x1024x24 +extension GLX -xkbdir root/usr/share/X11/xkb`. Then
  `DISPLAY=:77`. It runs with the sandbox on.
- A launcher for it already exists: run `unshare -r -m
  ~/.cache/xvfb/start.sh` in the background, then use `DISPLAY=:77`.
  Background commands are killed at their time limit: if `:77` is gone,
  start it again.
- Stop the Xvfb you started before you finish (`pkill -f 'Xvfb :77'`).
  A headless session doesn't exit while it runs, and the worker loop
  waits for it.
- **Web pages:** no browser is installed. Screenshot a page in Playwright's
  Chromium: `uv venv ~/.cache/pw-venv`, `uv pip install -p
  ~/.cache/pw-venv/bin/python playwright`, then
  `~/.cache/pw-venv/bin/python -m playwright install
  chromium-headless-shell`.
