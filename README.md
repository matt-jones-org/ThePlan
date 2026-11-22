# Crownfall — The Last Banner

A single-player conquest game for the browser. You command the blue house on a 3x3 map of strongholds and win by holding six of the nine, or the most land when round 30 ends. The rules engine is Python 3.12 standard library only; rival houses are played by simple local opponents, or optionally by Claude and GPT.

```sh
python -m engine.server                    # then open http://127.0.0.1:8000
python -m unittest discover -s tests -v    # 8 tests
```

Click **Raise your banner** to start. Demo mode is the default: deterministic local opponents, no API keys, no cost. Live Claude/GPT opponents need server-side keys and an access token (see below) and have not yet been verified against the real APIs.

Layout: `engine/game.py` (rules), `engine/agents.py` (model adapters), `engine/server.py` (HTTP API + SQLite), `web/index.html` (the whole client).

## Play

Orders resolve every four seconds. If you don't issue one, your selected stronghold holds and gathers supplies. Campaigns persist in SQLite, and **Continue campaign** restores the browser's last one.

| Control | Action |
| --- | --- |
| Click or tap your castle | Select your stronghold |
| Click a connected enemy castle | Queue an attack |
| Arrow keys / 1–9 | Select a stronghold |
| R | Recruit three soldiers for three gold |
| F | Add a wall level for three gold |
| G | Gather four additional gold |
| A, arrows, Enter | Choose and confirm an attack target |
| Space / Escape | Pause or resume |
| M | Toggle synthesized sound |
| ? / H | Open the field manual |

The game pauses when its window loses focus. Sound starts muted and is synthesized with Web Audio. Reduced-motion preferences calm the environmental animation and turn off combat shake. Everything on the battlefield is drawn procedurally on Canvas, so there are no art assets; Google Fonts load if available, with local fallbacks.

## Rules

Nine strongholds on a 3×3 road network. Every house starts with three strongholds, three soldiers at each stronghold, and six gold. Each round grants one gold per owned stronghold. Every house issues one order each round.

Gather adds four gold. Recruit costs three gold and adds three soldiers. Fortify costs three gold and adds one defense level, up to three. Costs must be affordable before the round's income.

An attack commits every soldier except one defender. Attack strength is committed soldiers plus a seeded d6; defense is defending soldiers plus walls plus a seeded d6. Ties favor defenders. Successful attackers occupy with `max(1, committed - defending soldiers)` and remove walls. Failed attacks reduce the defenders by `max(1, committed // 2)`, leaving at least one survivor.

Economy resolves first. Combat initiative rotates each round. Attacks cancel if their source has already fallen or no longer has enough soldiers. Six strongholds wins. At round 30, the largest kingdom wins; tied leaders draw. Losing every stronghold ends the player's campaign immediately.

## Live Claude + GPT opponents

Use host-managed secrets from `.env.example`; Python does not automatically load that file. The engine integrates Anthropic and OpenAI APIs. API billing is separate from Claude or ChatGPT subscriptions.

| House | Role | Provider | Default model | Environment override |
| --- | --- | --- | --- | --- |
| Aurora / blue | Strategist | Anthropic | `claude-sonnet-4-5` | `CLAUDE_STRATEGIST_MODEL` |
| Ember / red | Tactician | OpenAI | `gpt-4.1-mini` | `GPT_TACTICIAN_MODEL` |
| Verdant / violet | Scout | Anthropic | `claude-haiku-4-5` | `CLAUDE_SCOUT_MODEL` |

Set `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `PLAY_ACCESS_TOKEN` on the server. For deployed live play, your authenticated website backend must inject the engine bearer token server-side. Access `/play/?mode=live` through that backend. Default mode is free/demo. The browser has no token field and no provider secrets. Model IDs are configurable; verify availability with the provider accounts.

Each live round makes up to three parallel model calls, including the Aurora adviser whose proposal is overridden by direct player commands. These roles use the same game snapshot; only deterministic engine rules can change the state. Output is capped at 300 tokens per call with a 35-second timeout. Models get no tools and failed calls are not retried automatically. The next four-second countdown starts only after all calls return, so live rounds run slower than demo rounds.

Provider failure or an invalid model order does not commit the round. The game pauses and lets the player retry; a retry can incur new charges. Live API calls have not been verified yet: the provider adapters are only tested against mocked responses.

## Architecture and API

- `web/index.html`: Canvas rendering, animation loop, mouse/touch and keyboard input, sound. It holds no rules; it posts orders and draws the result.
- `engine/game.py`: authoritative rules, validation, seeded resolution and the demo opponents.
- `engine/agents.py`: Claude/GPT adapters and bounded parallel planning.
- `engine/server.py`: HTTP API, SQLite campaigns and an atomic per-turn journal with before/after state hashes.

| Method | Path | Request / result |
| --- | --- | --- |
| GET | `/api/health` | Status and model metadata; no secrets |
| POST | `/api/games` | `{ "mode": "demo", "seed": 42 }` → game |
| GET | `/api/games/{id}` | Persisted game |
| POST | `/api/games/{id}/turn` | `{ "expected_turn": 0, "order": { "action": "recruit", "source": 0 } }` → game and orders |

Province IDs are 0–8. An attack also needs `target`. Omit `order` to delegate Aurora to its adviser; the game's direct controls normally supply orders. Live creation, reads, and rounds require `Authorization: Bearer <PLAY_ACCESS_TOKEN>`. JSON requests only; no CORS allowances. Invalid/stale orders return 400, concurrent rounds 409, denied live access 403, and provider failure 502.

## Put it on the website

Give Claude [CLAUDE_HANDOFF.md](CLAUDE_HANDOFF.md). Run one engine process behind the website backend with persistent storage. Proxy `/play/` to engine `/` and `/play/api/*` to `/api/*`. API paths are relative to the game's directory. The Dockerfile is an alternative for a backend host; persist `/data`.

This is a single-player pilot, not a deployed public service. A static-only website requires a separate backend host. Before paid public live play, the website backend must authenticate users, enforce campaign ownership, rate-limit requests, enforce daily quotas, and inject the shared engine token server-side. Strip client-supplied engine Authorization headers and set provider-side spending caps. Keep live mode unavailable until these controls exist. Public demo mode does not incur provider charges but still needs request limits and storage housekeeping.

Use one process: the global turn lock intentionally allows one round across all campaigns at a time. Scaling requires queued jobs and database-level concurrency control. Game IDs are unguessable demo access capabilities, not website accounts.

## Verification

```sh
python -m unittest discover -s tests -v
```

Eight tests cover seeded replay over 20 worlds, rule invariants, invalid orders, persistence, player overrides, stale rounds, rollback on provider failure, provider request shapes (mocked) and HTTP gameplay/access control. There are no automated browser tests in the repo; the client was checked in Chromium for the title screen, recruiting, keyboard attacks, round resolution, pause/resume, help, arrow and number keys, sound toggling and mobile layout. CI runs the unit tests on every push.
