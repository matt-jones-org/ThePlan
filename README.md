# Crownfall — The Last Banner

A playable fantasy conquest game built for a website. Command the blue kingdom, recruit soldiers, strengthen castles, and march on neighboring strongholds. Capture six of nine strongholds before nightfall to claim the crown.

The interface is a full-screen animated battlefield, with no AI branding or technical controls. Claude and GPT can drive rival kingdoms behind the scenes; the free local mode uses deterministic opponents.

## Play

Python 3.12+, no third-party dependencies:

```sh
python -m engine.server
```

Open http://127.0.0.1:8000, then **Raise your banner**. Orders resolve every four seconds. When you do not issue an order, your soldiers hold position and gather supplies. Campaigns persist in SQLite; **Continue campaign** restores the browser's last campaign.

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

The game pauses when its window loses focus. Sound starts muted and only plays after enabling it. Reduced-motion preferences reduce environmental motion and disable combat shake.

Animation includes swaying trees, marching squads with leg movement, idle soldiers, waving flags, chimney smoke, drifting cloud shadows, moving river glints, circling birds, pulsing selection rings, animated attack routes, reinforcement effects, combat particles, camera shake, victory bursts, and a dawn-to-dusk color shift. Terrain and castles render procedurally on Canvas; no downloaded art assets are required. Google Fonts are optional, with local font fallbacks.

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

Each live round makes up to three parallel model calls, including the Aurora adviser whose proposal is overridden by direct player commands. These roles use the same game snapshot; only deterministic engine rules can change the state. Output is capped at 300 tokens per call, with a 35-second timeout. No recursive spawning, tools, shell execution, or automatic retries. The game waits for provider completion before scheduling the next four-second round. Live rounds therefore take longer than local rounds.

Provider failure or an invalid model order does not commit the round. The game pauses and lets the player retry; a retry can incur new charges. Live API calls have not been verified because this workspace has no provider credentials.

## Architecture and API

- `web/index.html`: Canvas game, animation loop, touch/mouse and keyboard controls, Web Audio effects, and presentation.
- `engine/game.py`: authoritative rules, validation, seeded resolution, and local opponents.
- `engine/agents.py`: configurable Claude/GPT adapters and bounded parallel planning.
- `engine/server.py`: HTTP API and SQLite campaigns/atomic turn journals, including before/after hashes.

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

Eight tests cover seeded replay over 20 worlds, invariants, invalid orders, persistence, player overrides, stale rounds, provider rollback, provider contract mocks, and HTTP gameplay/access control. Chromium checks cover the title screen, recruitment, keyboard attack, round resolution, pause/resume, help, arrows, number keys, sound toggling, and mobile layout.
