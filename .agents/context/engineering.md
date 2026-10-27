# Engineering defaults

What every session here does, whatever the project. A project's
`.agents/context/engineering.md` adds its own stack and wins where the two
differ. This machine's own tools and gotchas (paths, a display, what's
installed) are in `.agents/context/machine.local.md`, not in git: read it
if it exists.

## Python tooling

- Use uv. A project's `tools/` may be a uv project: `uv sync --project
  tools` once, then `uv run --project tools python tools/<script>.py`.
- If a venv's Python fails to start ("No module named 'encodings'", after a
  Python upgrade), run `uv sync --project tools` again.

## Shell

- Wait for a long run with `run_in_background`, not `sleep`: a chained
  `sleep` is blocked. Give the run a `timeout` above its expected time.
- `pkill -f <pattern>` kills the shell itself if the pattern appears in
  the command line.
- Stop what you started before you finish: a display server, a local web
  server, a watcher. A headless session doesn't exit while one runs, and
  the worker loop waits for it.

## Worktrees

The Agent tool's `isolation: "worktree"` fails (`.claude` is a symlink).
Use `git -C ../<project> worktree add <scratchpad>/wt-<slug> -b <branch>`.
It has no ignored folders (such as `artifacts/`): link the project's in
and don't commit the link. Issues stay in this repo's `.scratch/<project>/`.
Merge the branch and `git worktree remove` it when done.

## Screenshots and display

- **No display** (no `DISPLAY`, `/tmp/.X11-unix` empty): run a private
  Xvfb without root. `apt-get download xvfb libunwind8 libxfont2
  libfontenc1 xkb-data x11-xkb-utils xserver-common libxkbfile1`, `dpkg -x`
  each into a scratch `root/`, then start it inside `unshare -r -m`,
  bind-mounting a copy of `/usr/bin` with `xkbcomp` added over `/usr/bin`
  (Xvfb only looks for `/usr/bin/xkbcomp`), with
  `LD_LIBRARY_PATH=root/usr/lib/x86_64-linux-gnu` and `Xvfb :<n> -screen 0
  1280x1024x24 +extension GLX -xkbdir root/usr/share/X11/xkb`. Then
  `DISPLAY=:<n>`. Mesa's software GL is enough for OpenGL captures. Start
  it in the background; background commands are killed at their time
  limit, so start it again if it's gone, and stop it before you finish.
- **Web pages without a browser:** screenshot a page in Playwright's
  headless Chromium: `uv venv ~/.cache/pw-venv`, `uv pip install -p
  ~/.cache/pw-venv/bin/python playwright`, then
  `~/.cache/pw-venv/bin/python -m playwright install
  chromium-headless-shell`.
