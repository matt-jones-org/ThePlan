# Give this brief to Claude

Integrate **Crownfall — The Last Banner**, a playable fantasy conquest game, into my website. The game must feel like a game: no AI dashboard, model selectors, technical panels, or provider branding in the player experience.

**Game source:** https://github.com/matt-jones-org/ThePlan/pull/1 — branch `feat/multi-model-strategy-engine` until merged. Read `README.md`, `web/index.html`, and `engine/server.py` first.

**Website details to supply or inspect:**

- Website URL, repository, and branch.
- Hosting provider and available backend runtime.
- Desired game route, suggested `/play/`.
- Private pilot, free public demo, or authenticated live play.
- Existing login provider.
- Branding requirements and expected player traffic.
- Daily API spending cap if using live opponents.

**Preserve the game:** full-screen animated Canvas battlefield, castles, marching soldiers, waving banners, particle effects, keyboard and touch/mouse controls, sound toggle, title screen, pause, help, campaign continuation, and victory/defeat. Players command the blue kingdom and capture six of nine strongholds. Orders resolve every four seconds in free mode. Claude and GPT power rival decisions behind the scenes in live mode.

**Run the backend:** `python -m engine.server --host 127.0.0.1 --port 8000 --db /persistent/path/theplan.sqlite3`. Python 3.12+, no dependencies. One process only. Alternatively deploy the Dockerfile on a private service network with a persistent `/data` volume. Static hosting alone cannot run this backend.

**Website routing:** proxy `/play/` to engine `/` and `/play/api/*` to `/api/*`. Set proxy timeout to at least 60 seconds, disable caching for game responses, and make sure login/limits cannot be bypassed. Use a full-page route or a full-size iframe with keyboard focus rather than a small embedded dashboard.

**Secrets:** configure `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and a strong random `PLAY_ACCESS_TOKEN` in hosting secret settings, never in chat, public JavaScript, URLs, or source control. Optional model overrides are listed in `.env.example`. Verify model availability. Anthropic and OpenAI API accounts are separate from Claude/ChatGPT subscriptions.

**Launch free mode first:** `/play/` uses free local opponents, requires no provider credentials, and is fully playable. Test the final website route before enabling live mode.

**Public live mode:** `/play/?mode=live` requests model opponents. The website backend must authenticate each player, associate campaign IDs with owners, verify ownership on reads/rounds, enforce per-player/IP rate limits and daily spending quotas, and inject `Authorization: Bearer <PLAY_ACCESS_TOKEN>` only on server-to-engine requests. Strip client-supplied engine Authorization headers. Never expose the shared token to browsers. Set provider project budgets. Keep live unavailable until this protection exists. One live round uses up to three calls; model latency lengthens rounds.

**API contract:**

- `POST /api/games` with `{ "mode": "demo" | "live", "seed": 42 }` returns `{ id, mode, state }`.
- `GET /api/games/{id}` restores persisted state.
- `POST /api/games/{id}/turn` with `{ "expected_turn": 0, "order": { "action": "recruit", "source": 0 } }` returns updated state and orders. Actions: `gather`, `recruit`, `fortify`, `attack`; attack adds `target`. IDs are 0–8. Omit order to delegate. The game normally issues direct player orders or holds position and gathers.
- `GET /api/health` returns readiness and configured models without secrets.

**Acceptance:** run Python tests. On the final website route, verify title → start → select → recruit → attack → capture → victory/defeat; keyboard arrows/1–9/R/F/G/A/Enter/Space/M/?; mobile touch; pause on lost focus; Continue campaign after refresh; persistence after backend restart; sound requiring interaction. Verify provider failure pauses without committing state. Before live release, test both providers with host-managed secrets and prove logged-out users cannot trigger paid calls or read another user's campaigns.

Give me the deployed game URL, test results, and remaining hosting limitations. Do not claim live integration is verified until real Anthropic and OpenAI calls succeed. For larger traffic, add a queue and database-level concurrency control before adding workers.
