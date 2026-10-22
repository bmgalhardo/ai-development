# The games server

Every output is published to the games server,
https://games.bgalhardo.internal: the same route for Claude and Codex.
It is on the LAN and the VPN only, and it has no auth. It keeps only the
latest build of each output. Everything it serves can be rebuilt from the
game's repo and this repo's `.scratch/`.

```
/                    the menu of games
/<game>/             the game's menu: Game, Docs, Mocks
/<game>/game/        /<game>/docs/        /<game>/mocks/
```

Publish with:

```bash
python3 tools/publish/publish.py ../<game>
```

- It reads the outputs and their prepared folders from the game's
  `.agents/context/publishing.md` (the `game` and `docs` rows).
- The docs carry the current review (`docs/review.md`).
- It publishes the current cycle's `mocks/` (`.scratch/<game>/<cycle>/`)
  as the Mocks page, newest first, when there are any.
- An output the game no longer has is removed from the server.
- It uploads each output to a staging folder and then moves it into
  place, so the previous build stays up until the new one is complete.
- It rebuilds both menus and prints each link. Return those links.
- Prepare each output first (the game's engineering doc says how). The
  script stops if an output's `index.html` is missing.
- A failed upload stops the script with the HTTP error. Report it as the
  blocker; local files alone are not a publication.

The server is a WebDAV nginx in the homelab's k8s cluster (`games` in the
`system` namespace). `GAMES_URL` points the script at another server.
