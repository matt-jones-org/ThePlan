# Brief for Claude: put ThePlan on my website

Copy the following into Claude, filling in the website details. Never paste provider secrets into chat.

---

Integrate **ThePlan / Frontier Command**, a playable multi-agent strategy simulation, into my existing website.

**Source:** https://github.com/matt-jones-org/ThePlan. Use the `feat/multi-model-strategy-engine` branch / its pull request until merged. Read `README.md`, `engine/server.py`, and `web/index.html` before changing anything.

**My website details:**

- Website URL: [fill in]
- Website repository and branch: [fill in]
- Hosting provider and backend runtime: [fill in, or inspect existing deployment]
- Desired URL: `/play/` [change if needed]
- Access: [private pilot / logged-in users / public demo]
- Login provider, if any: [fill in or inspect]
- Branding and mobile design requirements: [fill in]
- Live API budget and player limits: [fill in]

**Experience:** players command Aurora, issue orders or delegate to Claude, and fight GPT and a second Claude model on a 3×3 province map. Provide a working free demo and clearly label live mode. Show turn progress, model failures, faction state, game-over results, and a new-game action. Preserve direct player control and mobile usability.

**Backend:** run `python -m engine.server --host 127.0.0.1 --port 8000 --db /persistent/path/theplan.sqlite3` as one process behind the website backend, or deploy the provided container on a private service network. Persist SQLite outside ephemeral deployments. Static hosting alone cannot run the engine. Do not deploy additional workers against this SQLite pilot.

**Routing:** proxy `/play/` to engine `/`; proxy `/play/api/*` to `/api/*`, or adapt the UI to equivalent same-origin website backend routes. Configure the reverse proxy timeout above the 35-second provider deadline (for example 60 seconds). Do not cache game responses. Make sure the public proxy cannot bypass authentication or rate limits.

**Credentials:** configure `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and a strong random `PLAY_ACCESS_TOKEN` using the hosting provider's secret settings. Optional model overrides: `CLAUDE_STRATEGIST_MODEL`, `CLAUDE_SCOUT_MODEL`, `GPT_TACTICIAN_MODEL`. Confirm model access with these accounts. Neither a Claude subscription nor a ChatGPT subscription provides these API credentials.

**Public live access:** authenticate the player in the website backend, map each campaign ID to its owner, verify ownership on reads and turns, enforce per-user/IP creation and turn limits plus daily API quotas, then attach `Authorization: Bearer <PLAY_ACCESS_TOKEN>` on the server-to-engine request. Never expose that shared token or provider keys to public client code. Strip client-supplied engine Authorization headers. Remove the pilot token field from the website UI. Set provider spending limits. If authentication and spend controls are not configured, launch demo mode only and keep live mode disabled.

**API:**

1. `GET /api/health`: provider/model metadata.
2. `POST /api/games` with `{ "mode": "demo" | "live", "seed": 42 }`: returns `{ id, mode, state }` (and initially empty `orders`).
3. `GET /api/games/{id}`: resume campaign. Store the campaign ID with the logged-in owner, not in public logs.
4. `POST /api/games/{id}/turn` with `{ "expected_turn": 0, "directive": "Protect the center", "order": { "action": "recruit", "source": 0 } }`: persists one turn and returns game + faction orders. Omit `order` for delegation. Attack orders need `target`. IDs are zero-based; UI labels start at one.

**Acceptance checks:** run the Python test suite; play demo through several turns; verify resume after restart; test phone layout; verify invalid orders and stale turns don't advance state; verify live authorization and ownership; test a live turn using host-managed secrets; simulate a provider failure and verify state doesn't advance; check logged-out users cannot trigger paid calls; verify daily limits and proxy routing at the final URL.

Provide the final website URL, deployment changes, test results, and any remaining limits. Do not claim live model integration has been verified until both Anthropic and OpenAI calls succeed in the deployed environment.
