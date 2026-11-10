# ThePlan — Frontier Command

A playable multi-agent strategy simulation. You command Aurora on a nine-province map while Claude and GPT command rival factions. Issue a direct order or delegate to your Claude strategist. Model agents plan in parallel against the same turn snapshot; deterministic Python rules resolve the outcome.

## Play locally

Requires Python 3.12+; no third-party dependencies.

```sh
python -m engine.server
```

Open http://127.0.0.1:8000 and start an **Offline demo** campaign. Pick an Aurora province, choose an action, and resolve a turn. Games persist in SQLite and the browser remembers the last game ID. Demo agents use local heuristics and never call providers. Strategy text influences the Aurora agent in live mode; direct orders work in both modes.

## Claude + GPT live play

Configure environment variables from `.env.example` in your host's secret settings, then restart the server. This application does not load `.env` files automatically. API keys stay server-side. For a private local pilot, generate a long random `PLAY_ACCESS_TOKEN`, set it on the server, and enter that access token in the game's password field. This token is separate from both provider API keys and is held only in browser memory. Reloading requires entering it again. Do not share the pilot token on a public website.

| Faction | Agent role | Provider | Default model | Override |
| --- | --- | --- | --- | --- |
| Aurora | Your strategist | Anthropic | `claude-sonnet-4-5` | `CLAUDE_STRATEGIST_MODEL` |
| Ember | Rival tactician | OpenAI | `gpt-4.1-mini` | `GPT_TACTICIAN_MODEL` |
| Verdant | Rival scout | Anthropic | `claude-haiku-4-5` | `CLAUDE_SCOUT_MODEL` |

Model IDs are configurable; confirm availability for your provider accounts. This integrates the **Anthropic API**, not a Claude subscription or Claude website session. Likewise, OpenAI API billing is separate from ChatGPT subscriptions. No provider credentials were available during implementation, so live calls require verification in your account.

Each live turn makes up to three provider requests, including Aurora even when the player overrides its order. Output is capped at 300 tokens per request; input includes the current state and the last 100 log entries. Requests have a 35-second timeout. There are no automatic retries, background loops, tool execution, or recursive agent spawning. A provider failure or invalid order leaves the turn uncommitted and reports an error; it never silently changes to demo mode. A retry can incur new provider charges.

## Rules

- Nine provinces on a 3×3 orthogonal grid. Each faction starts with three provinces, three troops per province, and six gold.
- Each faction selects one order per turn. Every active faction gains one gold per owned province; costs are validated against the pre-turn balance.
- Gather adds four gold; recruit costs three gold for three troops; fortify costs three gold for one defense level, up to three.
- Attack an adjacent enemy with all source troops except one. Attack strength is committed troops plus d6; defense is defending troops plus fort plus d6. Ties favor the defender. A successful attacker occupies with `max(1, committed troops - defending troops)` and removes the fort. On failure, defenders lose `max(1, committed troops // 2)` troops, with at least one survivor.
- Economy orders resolve before attacks. Combat initiative rotates Aurora → Ember → Verdant each turn. An attack is cancelled if its source has since been captured or reduced to one troop. RNG is seeded by world seed and turn for reproducible resolution.
- Six provinces wins immediately after resolution. At turn 30, most provinces wins; a tied lead is a draw. Eliminated factions stop receiving orders.

## Engine and API

`engine/game.py` owns all rules and validation. `engine/agents.py` owns provider adapters and bounded parallel planning. `engine/server.py` serves the game and stores campaigns and turn journals atomically in SQLite, including orders and before/after state hashes.

| Method | Path | Body / response |
| --- | --- | --- |
| GET | `/api/health` | Status and configured model IDs; no secrets |
| POST | `/api/games` | `{ "mode": "demo", "seed": 42 }` → game |
| GET | `/api/games/{id}` | Persisted game |
| POST | `/api/games/{id}/turn` | `{ "expected_turn": 0, "directive": "Hold the center", "order": { "action": "recruit", "source": 0 } }` → game + orders |

`order` is optional; omit it to delegate Aurora's move. `attack` also needs `target`. Province IDs are 0–8; UI labels are 1–9. Live game creation, reads, and turns require `Authorization: Bearer <PLAY_ACCESS_TOKEN>`. JSON requests only; no CORS allowances. A stale turn returns 400; concurrent turns return 409; invalid live access returns 403; provider errors return 502. Game IDs are unguessable bearer capabilities for demo campaigns; they are not a user account system.

## Website integration

See [CLAUDE_HANDOFF.md](CLAUDE_HANDOFF.md) for a ready-to-send implementation brief. This is a runnable single-process pilot, not a deployed public multiplayer service. Bind it to localhost behind your website backend or a private service network. Run exactly one process with persistent storage. The global turn lock intentionally allows only one turn across all games at a time. For broader traffic, add a job queue and database-level concurrency control.

The browser interface can be mounted at `/play/` if the website proxies `/play/api/*` to the engine's `/api/*` and `/play/` to `/`. Its API URLs are relative. A static-only website needs a separate backend host. The Dockerfile supplies a container option; mount a persistent volume at `/data`.

Before public paid play, your website backend must authenticate users, enforce campaign ownership, apply per-user/IP rate limits and daily spend quotas, and inject the engine access token server-side. Remove the pilot token field for that deployment. Set provider-side project spending limits. Do not put provider keys or the shared engine access token in public JavaScript. The pilot does not implement website login, per-user billing, distributed jobs, multiplayer matchmaking, or streaming.

## Verify

```sh
python -m unittest discover -s tests -v
```

Tests cover deterministic replay over 20 seeds, state invariants, invalid orders, player overrides, persistence, stale turns, provider failure rollback, mocked Anthropic/OpenAI request contracts, and HTTP gameplay/authentication.
