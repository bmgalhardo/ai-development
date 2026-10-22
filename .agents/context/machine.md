# This machine: tools and gotchas

What every game finds on this machine, and how to use it. A game's
engineering doc says which of these it uses, with its own paths and
commands.

## Godot

- Use the standard (non-.NET) Linux build that each game keeps in its own
  `artifacts/godot/`. Its engineering doc names the version.
- `/snap/bin/godot-4` is the .NET build. It runs projects but **cannot
  export Web**.
- Headless Firefox has no WebGL2 here. Check a Web build in Playwright's
  headless Chromium (below), which renders with software WebGL. It is
  slow: report its times as this machine's, not the phone's.

## Python

- uv is at `~/.local/bin/uv`. A game's `tools/` may be a uv project:
  `uv sync --project tools` once, then
  `uv run --project tools python tools/<script>.py`.
- If a venv's Python fails to start ("No module named 'encodings'", after a
  Python upgrade), run `uv sync --project tools` again.
- The system Python has no PIL. To read or convert images, use a uv
  venv with pillow: `uv venv ~/.cache/img-venv`, then
  `uv pip install -p ~/.cache/img-venv/bin/python pillow`.
- `/tmp` is small. Put venvs and downloads under `~/.cache/` or the
  scratchpad.

## Screenshots and display

- Use `DISPLAY=:0`. If it isn't there, use the private Xvfb on `:77`
  (below). Mesa's software GL is enough for Godot captures.
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
- **Web pages:** no browser is installed. Screenshot a page in Playwright's
  Chromium: `uv venv ~/.cache/pw-venv`, `uv pip install -p
  ~/.cache/pw-venv/bin/python playwright`, then
  `~/.cache/pw-venv/bin/python -m playwright install
  chromium-headless-shell`.

## Worktrees

The Agent tool's `isolation: "worktree"` fails (`.claude` is a symlink).
Use `git -C ../<game> worktree add <scratchpad>/wt-<slug> -b <branch>`.
It has no `artifacts/` (not in git): link the game's `artifacts/` in and
don't commit the link. Issues stay in this repo's `.scratch/<game>/`.
Merge the branch and `git worktree remove` it when done.

## Shell

- Wait for a long run with `run_in_background`, not `sleep`: a chained
  `sleep` is blocked. Give the run a `timeout` above its expected time.
- `pkill -f <pattern>` kills the shell itself if the pattern appears in
  the command line.

## Blender (remote, on hephaestus)

The user authorizes routine Blender runs and their script and image
transfers on hephaestus (12 Oct 2026). Do not ask for permission for each
run.

This machine is too small for Blender. It runs headless on another machine,
reached with `ssh hephaestus`: Blender 4.5 LTS, 12 CPU cores, 16 GB RAM,
**no GPU**. Cycles renders on the CPU. EEVEE and viewport renders don't work
there.

- **Off by default:** if `ssh hephaestus` doesn't answer, ask the user to
  start it.
- **Scripts, not `.blend` files:** each model is a Blender Python script in
  the game's tools that builds the scene from scratch
  (`bpy.ops.wm.read_factory_settings(use_empty=True)` first) and writes its
  output to the folder given after `--`. The script is the source.
  `.blend` files stay out of git.
- **Round trip:**
  ```sh
  scp <script>.py hephaestus:work/
  ssh hephaestus 'blender -b --python work/<script>.py -- out/'
  scp 'hephaestus:out/<model>.glb' <game asset folder>/
  ```
  Check the result in the game (a Godot capture) before using it.
- **Memory:** low-poly exports and test renders need well under 1 GB. A
  high-to-low-poly bake can use several GB. Above 16 GB Blender is killed.
