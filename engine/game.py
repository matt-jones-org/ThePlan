"""Deterministic game rules. Models propose orders; only this module mutates state."""
from copy import deepcopy
import hashlib
import random

FACTIONS = ("aurora", "ember", "verdant")
ACTIONS = ("gather", "recruit", "attack", "fortify")


def new_game(seed=42):
    return {
        "seed": seed, "turn": 0, "winner": None,
        "factions": {f: {"gold": 6, "score": 3} for f in FACTIONS},
        "regions": [
            {"id": i, "owner": FACTIONS[i // 3], "troops": 3, "fort": 0}
            for i in range(9)
        ],
        "log": ["Three factions contest the nine provinces. First to six provinces wins."],
    }


def adjacent(a, b):
    return abs(a // 3 - b // 3) + abs(a % 3 - b % 3) == 1


def validate_order(state, faction, order):
    if not isinstance(order, dict) or order.get("action") not in ACTIONS:
        raise ValueError("Unknown action")
    source = order.get("source")
    if type(source) is not int or not 0 <= source < 9:
        raise ValueError("Source must be a province ID from 0 to 8")
    region = state["regions"][source]
    if region["owner"] != faction:
        raise ValueError("Source province belongs to another faction")
    action = order["action"]
    if action in ("recruit", "fortify") and state["factions"][faction]["gold"] < 3:
        raise ValueError("Insufficient gold")
    if action == "attack":
        target = order.get("target")
        if type(target) is not int or not 0 <= target < 9 or not adjacent(source, target):
            raise ValueError("Attack target must be adjacent")
        if state["regions"][target]["owner"] == faction or region["troops"] < 2:
            raise ValueError("Attack needs an enemy target and at least two troops")
    if action == "fortify" and region["fort"] >= 3:
        raise ValueError("Fortification already at maximum")
    return {"action": action, "source": source,
            "target": order.get("target") if action == "attack" else None,
            "reason": str(order.get("reason", ""))[:500]}


def resolve(state, orders):
    """Validate against one snapshot, apply economy then seeded rotating combat."""
    if state["winner"]:
        raise ValueError("Game has ended")
    active = {r["owner"] for r in state["regions"]}
    if set(orders) != active:
        raise ValueError("Exactly one order per active faction is required")
    clean = {f: validate_order(state, f, orders[f]) for f in active}
    result = deepcopy(state)
    result["turn"] += 1
    events = []
    for f in FACTIONS:
        if f not in active:
            continue
        order = clean[f]
        region = result["regions"][order["source"]]
        action = order["action"]
        result["factions"][f]["gold"] += sum(r["owner"] == f for r in state["regions"])
        if action == "gather":
            result["factions"][f]["gold"] += 4
        elif action == "recruit":
            result["factions"][f]["gold"] -= 3
            region["troops"] += 3
        elif action == "fortify":
            result["factions"][f]["gold"] -= 3
            region["fort"] += 1
        events.append(f"{f.title()}: {action} in province {order['source'] + 1}.")
    initiative = list(FACTIONS)
    offset = (result["turn"] - 1) % 3
    initiative = initiative[offset:] + initiative[:offset]
    rng = random.Random(f"{state['seed']}:{result['turn']}")
    for f in initiative:
        order = clean.get(f)
        if not order or order["action"] != "attack":
            continue
        source = result["regions"][order["source"]]
        target = result["regions"][order["target"]]
        if source["owner"] != f or source["troops"] < 2 or target["owner"] == f:
            events.append(f"{f.title()}'s attack cancelled after the battlefield changed.")
            continue
        force = source["troops"] - 1
        source["troops"] = 1
        attack = force + rng.randint(1, 6)
        defense = target["troops"] + target["fort"] + rng.randint(1, 6)
        if attack > defense:
            target.update(owner=f, troops=max(1, force - target["troops"]), fort=0)
            events.append(f"{f.title()} captures province {target['id'] + 1}!")
        else:
            target["troops"] = max(1, target["troops"] - max(1, force // 2))
            events.append(f"{f.title()}'s attack on province {target['id'] + 1} is repelled.")
    for f in FACTIONS:
        count = sum(r["owner"] == f for r in result["regions"])
        result["factions"][f]["score"] = count
        if count >= 6:
            result["winner"] = f
    if result["turn"] >= 30 and not result["winner"]:
        scores = {f: sum(r["owner"] == f for r in result["regions"]) for f in FACTIONS}
        leaders = [f for f, score in scores.items() if score == max(scores.values())]
        result["winner"] = leaders[0] if len(leaders) == 1 else "draw"
    result["log"] = (result["log"] + events)[-100:]
    return result


def demo_order(state, faction):
    owned = [r for r in state["regions"] if r["owner"] == faction]
    border = [r for r in owned if any(adjacent(r["id"], t["id"]) and t["owner"] != faction
                                    for t in state["regions"])]
    source = max(border or owned, key=lambda r: r["troops"])
    enemies = [t for t in state["regions"] if adjacent(source["id"], t["id"]) and t["owner"] != faction]
    if enemies and source["troops"] >= 5:
        target = min(enemies, key=lambda r: r["troops"] + r["fort"])
        return {"action": "attack", "source": source["id"], "target": target["id"], "reason": "Advance on the weakest adjacent province."}
    return {"action": "recruit" if state["factions"][faction]["gold"] >= 3 else "gather",
            "source": source["id"], "reason": "Build strength along the frontier."}


def state_hash(state):
    import json
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
