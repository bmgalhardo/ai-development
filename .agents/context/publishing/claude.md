# Publishing in Claude

Use the Artifact tools. The game's publishing doc lists its outputs, the
prepared files for each and its Claude destinations. Reuse each
destination: update it in place, never create a new one on each
publication.

## Updating

The Artifact tool refuses to overwrite files this session hasn't seen.
Read the artifact, then read with `paths` each file the publication will
replace, including changed images and binaries. For a multi-file output,
list its files with `scope: "files"`. Publish the root `index.html` plus a
`files` mapping for new or changed dependencies. Verify success and return
the link.

- **Docs page:** include `img/`. Comments (composer only) and "Send to
  Claude" reach a watching session. Edit the Markdown, not the generated
  page.
- **Review board:** build it with `python3 tools/render_review.py ../<game>`;
  the prepared files are this repo's `artifacts/review/<game>/`. Include
  `assets/`, `img/` and the mock pages. No comment buttons or declared
  capabilities.
- **Game (a Godot Web export):** include every file the game's package
  writes (for example `index.js` and the `.wasm` files).

## Host constraints

- Artifacts serve `.wasm` but not `.pck` or `.gz`, and cap binaries at
  15 MB. A Godot Web export has to be packaged for that (the game's
  engineering doc says how its package does it).
- The Artifact tool reads only the session's working directory and
  scratchpad. A game's prepared files are outside both: copy them to the
  scratchpad and publish from there (`root` plus `files`).
