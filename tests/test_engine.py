import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from engine.agents import ProviderError, model_order, plan_turn
from engine.game import FACTIONS, demo_order, new_game, resolve, state_hash, validate_order
from engine.server import Store, make_handler


class RulesTests(unittest.TestCase):
    def test_replay_and_invariants(self):
        for seed in range(20):
            state = new_game(seed)
            for _ in range(30):
                if state['winner']:
                    break
                before = state_hash(state)
                orders = plan_turn(state, '', 'demo')
                next_state = resolve(state, orders)
                self.assertEqual(next_state, resolve(state, orders))
                self.assertEqual(before, state_hash(state))
                self.assertEqual(len(next_state['regions']), 9)
                for region in next_state['regions']:
                    self.assertGreaterEqual(region['troops'], 1)
                    self.assertIn(region['owner'], FACTIONS)
                for faction in next_state['factions'].values():
                    self.assertGreaterEqual(faction['gold'], 0)
                state = next_state
            self.assertIsNotNone(state['winner'])

    def test_invalid_orders(self):
        for order in [[], {'action':'attack','source':0,'target':8},
                      {'action':'gather','source':3}, {'action':'gather','source':True}]:
            with self.assertRaises(ValueError):
                validate_order(new_game(), 'aurora', order)

    def test_player_order_and_stale_turn(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(str(Path(folder) / 'test.db'))
            game = store.create('demo', 42)
            result = store.turn(game['id'], 0, '', {'action':'gather','source':0})
            self.assertEqual(result['state']['factions']['aurora']['gold'], 13)
            self.assertEqual(store.read(game['id'])['state'], result['state'])
            with self.assertRaises(ValueError):
                store.turn(game['id'], 0, '')

    def test_provider_failure_does_not_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(str(Path(folder) / 'test.db'))
            game = store.create('live', 42)
            with patch('engine.server.plan_turn', side_effect=ProviderError('offline')):
                with self.assertRaises(ProviderError):
                    store.turn(game['id'], 0, '')
            self.assertEqual(store.read(game['id'])['state']['turn'], 0)
            with store.connect() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM turns').fetchone()[0], 0)

    @patch.dict(os.environ, {'ANTHROPIC_API_KEY':'test', 'OPENAI_API_KEY':'test'})
    def test_provider_contracts(self):
        calls = []
        def fake(url, payload, headers):
            calls.append((url, payload, headers))
            if 'anthropic' in url:
                return {'content':[{'type':'text','text':'{"action":"recruit","source":0}'}]}
            return {'choices':[{'message':{'content':'{"action":"recruit","source":3}'}}]}
        self.assertEqual(model_order(new_game(), 'aurora', 'defend', fake)['source'], 0)
        self.assertEqual(model_order(new_game(), 'ember', 'defend', fake)['source'], 3)
        self.assertEqual(calls[0][1]['max_tokens'], 300)
        self.assertEqual(calls[1][1]['response_format'], {'type':'json_object'})
        self.assertNotIn('defend', calls[1][1]['messages'][1]['content'])
        with self.assertRaises(ProviderError):
            model_order(new_game(), 'aurora', '', lambda *_: {'content':[]})


class APITests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(Store(str(Path(self.folder.name)/'test.db'))))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.folder.cleanup()

    def request(self, path, data=None):
        req = urllib.request.Request(self.base+path, json.dumps(data).encode() if data is not None else None,
                                     {'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as response:
            return json.load(response)

    def test_playable_round_trip(self):
        game = self.request('/api/games', {'mode':'demo'})
        turn = self.request(f"/api/games/{game['id']}/turn", {'expected_turn':0, 'order':{'action':'gather','source':0}})
        self.assertEqual(turn['state']['turn'], 1)
        self.assertEqual(self.request(f"/api/games/{game['id']}")['state'], turn['state'])
        with urllib.request.urlopen(self.base+'/') as response:
            self.assertIn(b'CROWNFALL', response.read())

    @patch.dict(os.environ, {'PLAY_ACCESS_TOKEN':'private-test-token'})
    def test_unauthorized_live_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/games', {'mode':'live'})
        self.assertEqual(error.exception.code, 403)

    def test_malformed_request(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/games', [])
        self.assertEqual(error.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
