# Publishing in ChatGPT

Use the Sites skill and native Sites tools to create or update persistent,
openable results in ChatGPT. The user expects to return to them in the
app's Library. Verify the actual returned destination and explain how to
reopen it. Do not claim Library placement without confirmation from the
tools.

The game's publishing doc lists its outputs, the prepared files for each
and their Sites. Keep each output a separate Site. The review board's
prepared files are this repo's `artifacts/review/<game>/`, built with
`python3 tools/review/render_review.py ../<game>`. Read the installed Sites skill
for the current source, packaging and deployment procedure.

- Use a separate source checkout and `.openai/hosting.json` for each Site.
  Copy prepared static files into its `dist/`, preserving relative paths.
  Keep reusable checkouts in the game's `artifacts/sites/<output>/`
  (for example `game/`, `docs/`, `review/`).
- For a newly created Site, persist the project ID returned by Sites tools
  in that checkout's `.openai/hosting.json` before using the source helper.
  If its initial remote commit has no hosting manifest, preserve that commit
  and make a normal fast-forward source commit adding the manifest with the
  returned ID. Then run the documented sync, package and deploy flow. Never
  force-push or replace an existing source history to bootstrap a Site.
- Reuse each existing project ID. If a checkout is missing, recover the
  existing Site through native tools before creating a replacement.
  Do not create a new Site on each publication.
- New Sites are private. Preserve existing audiences unless the user
  requests a change.
- Follow the Sites skill to synchronize source, package the exact source,
  save and deploy. Keep credentials out of files and output.
- Confirm deployment succeeded and return its literal link. Local HTML
  or an undeployed version does not fulfill "publish", unless the user
  explicitly asked to save without deploying.

Claude Artifact URLs are separate destinations, not update targets for
Sites tools. If Sites publication is unavailable, finish the local
preparation and report the specific blocker.
