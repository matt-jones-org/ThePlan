"""Small local HTTP API with SQLite persistence and atomic game turns."""
import argparse
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .agents import ProviderError, configuration, plan_turn
from .game import new_game, resolve, state_hash, validate_order

WEB = Path(__file__).resolve().parent.parent / "web" / "index.html"


class Store:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS games (id TEXT PRIMARY KEY, mode TEXT, state TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS turns (game TEXT, turn INTEGER, record TEXT, PRIMARY KEY(game, turn))")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def create(self, mode, seed):
        game_id = secrets.token_urlsafe(24)
        state = new_game(seed)
        with self.connect() as db:
            db.execute("INSERT INTO games VALUES (?, ?, ?)", (game_id, mode, json.dumps(state)))
        return {"id": game_id, "mode": mode, "state": state, "orders": {}}

    def read(self, game_id):
        with self.connect() as db:
            row = db.execute("SELECT mode, state FROM games WHERE id=?", (game_id,)).fetchone()
        if not row:
            raise KeyError("Game not found")
        return {"id": game_id, "mode": row[0], "state": json.loads(row[1])}

    def turn(self, game_id, expected_turn, directive, player_order=None):
        # One global lock bounds provider concurrency and serializes state commits.
        if not self.lock.acquire(blocking=False):
            raise BlockingIOError("Another turn is running; try again shortly")
        try:
            game = self.read(game_id)
            before = game["state"]
            if before["turn"] != expected_turn:
                raise ValueError("Stale turn; reload the game before trying again")
            if before["winner"]:
                raise ValueError("Game has ended")
            if player_order is not None:
                player_order = validate_order(before, "aurora", player_order)
            orders = plan_turn(before, directive, game["mode"])
            if player_order is not None:
                orders["aurora"] = player_order
            after = resolve(before, orders)
            record = {"orders": orders, "directive": directive, "before_hash": state_hash(before),
                      "after_hash": state_hash(after), "state": after}
            with self.connect() as db:
                db.execute("UPDATE games SET state=? WHERE id=?", (json.dumps(after), game_id))
                db.execute("INSERT INTO turns VALUES (?, ?, ?)", (game_id, after["turn"], json.dumps(record)))
            return {**game, "state": after, "orders": orders}
        finally:
            self.lock.release()


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Game IDs are access capabilities; keep URLs out of default logs.

        def send_json(self, status, data):
            payload = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def authorized(self, mode):
            if mode != "live":
                return
            token = os.getenv("PLAY_ACCESS_TOKEN", "")
            supplied = self.headers.get("Authorization", "")
            if not token or not hmac.compare_digest(supplied, "Bearer " + token):
                raise PermissionError("Live play requires an authorized website backend or pilot access token")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                content = WEB.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(content)
            elif path == "/api/health":
                self.send_json(200, {"status": "ok", "agents": configuration(), "defaultMode": "demo"})
            elif path.startswith("/api/games/") and len(path.split("/")) == 4:
                try:
                    game = store.read(path.split("/")[3])
                    self.authorized(game["mode"])
                    self.send_json(200, game)
                except KeyError:
                    self.send_json(404, {"error": "Game not found"})
                except PermissionError as exc:
                    self.send_json(403, {"error": str(exc)})
            else:
                self.send_json(404, {"error": "Not found"})

        def do_POST(self):
            try:
                # Require JSON: cross-origin forms cannot submit paid game turns.
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Content-Type must be application/json")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    raise ValueError("Request body must be 1..8192 bytes")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object")
                if self.path == "/api/games":
                    mode = data.get("mode", "demo")
                    if mode not in ("demo", "live"):
                        raise ValueError("Mode must be demo or live")
                    self.authorized(mode)
                    seed = data.get("seed", 42)
                    if type(seed) is not int or not 0 <= seed <= 2147483647:
                        raise ValueError("Seed must be an integer from 0 to 2147483647")
                    self.send_json(201, store.create(mode, seed))
                elif self.path.startswith("/api/games/") and self.path.endswith("/turn") and len(self.path.split("/")) == 5:
                    game_id = self.path.split("/")[3]
                    self.authorized(store.read(game_id)["mode"])
                    expected = data.get("expected_turn")
                    directive = data.get("directive", "")
                    if type(expected) is not int or not isinstance(directive, str) or len(directive) > 1000:
                        raise ValueError("expected_turn must be an integer; directive must be at most 1000 characters")
                    self.send_json(200, store.turn(game_id, expected, directive, data.get("order")))
                else:
                    self.send_json(404, {"error": "Not found"})
            except PermissionError as exc:
                self.send_json(403, {"error": str(exc)})
            except KeyError:
                self.send_json(404, {"error": "Game not found"})
            except (ValueError, TypeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except BlockingIOError as exc:
                self.send_json(409, {"error": str(exc)})
            except ProviderError as exc:
                self.send_json(502, {"error": str(exc)})
            except Exception:
                self.send_json(500, {"error": "Internal server error; turn was not completed"})
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default="theplan.sqlite3")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(Store(args.db)))
    print(f"ThePlan ready at http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
