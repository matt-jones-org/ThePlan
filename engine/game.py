"""Deterministic game rules. Models propose orders; only this module mutates state.

State is a plain JSON-serializable dict so it can be stored, hashed and sent to
the browser or a model as-is. Provinces are numbered 0-8 on a 3x3 grid, row-major.
"""
from copy import deepcopy
import hashlib
import random

FACTIONS = ("aurora", "ember", "verdant")
ACTIONS = ("gather", "recruit", "attack", "fortify")


def new_game(seed=42):
    """Fresh state: each faction owns one row of the grid, 3 troops per province, 6 gold."""
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
    # Orthogonal neighbors only (Manhattan distance 1); no diagonals.
    return abs(a // 3 - b // 3) + abs(a % 3 - b % 3) == 1


def validate_order(state, faction, order):
    """Check an order against the given state and return a normalized copy.

    Raises ValueError on anything illegal. Order dicts come from players and
    models, so nothing in them is trusted.
    """
    if not isinstance(order, dict) or order.get("action") not in ACTIONS:
        raise ValueError("Unknown action")
    source = order.get("source")
    # type() rather than isinstance(): bool is a subclass of int and True would pass.
    if type(source) is not int or not 0 <= source < 9:
        raise ValueError("Source must be a province ID from 0 to 8")
    region = state["regions"][source]
    if region["owner"] != faction:
        raise ValueError("Source province belongs to another faction")
    action = order["action"]
    # Gold is checked before this round's income is paid out.
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
            # The reason is free text from a model; cap it before it gets persisted.
            "reason": str(order.get("reason", ""))[:500]}


def resolve(state, orders):
    """Validate against one snapshot, apply economy then seeded rotating combat.

    Returns a new state; the input is never modified. The same state and orders
    always produce the same result.
    """
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
        # Income is counted from the pre-turn snapshot, before any captures.
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
    # Attacks resolve one at a time, so whoever goes first can change the board
    # for the others. Rotate the order each turn so nobody keeps that edge.
    initiative = list(FACTIONS)
    offset = (result["turn"] - 1) % 3
    initiative = initiative[offset:] + initiative[:offset]
    # A string seed is hashed deterministically (unlike hash()), so replays match
    # across processes and PYTHONHASHSEED values.
    rng = random.Random(f"{state['seed']}:{result['turn']}")
    for f in initiative:
        order = clean.get(f)
        if not order or order["action"] != "attack":
            continue
        source = result["regions"][order["source"]]
        target = result["regions"][order["target"]]
        # Orders were validated against the pre-turn snapshot; an earlier attack
        # this turn may have taken the source or already won the target.
        if source["owner"] != f or source["troops"] < 2 or target["owner"] == f:
            events.append(f"{f.title()}'s attack cancelled after the battlefield changed.")
            continue
        # The committed force is spent either way: survivors garrison a captured
        # province, and a failed attack leaves only the one defender at home.
        force = source["troops"] - 1
        source["troops"] = 1
        attack = force + rng.randint(1, 6)
        defense = target["troops"] + target["fort"] + rng.randint(1, 6)
        if attack > defense:  # ties go to the defender
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
    # Nine provinces means at most one faction can hold six, so no tie-break above.
    if result["turn"] >= 30 and not result["winner"]:
        scores = {f: sum(r["owner"] == f for r in result["regions"]) for f in FACTIONS}
        leaders = [f for f, score in scores.items() if score == max(scores.values())]
        result["winner"] = leaders[0] if len(leaders) == 1 else "draw"
    # Keep the log bounded; the full history lives in the server's turn journal.
    result["log"] = (result["log"] + events)[-100:]
    return result


def demo_order(state, faction):
    """Simple deterministic opponent for demo mode: no API calls, no randomness.

    Works from its strongest border province: attacks the weakest neighbor once
    it has 5+ troops, otherwise recruits, or gathers when short of gold.
    """
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
    """SHA-256 of the canonical JSON form; recorded before and after each turn."""
    import json
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
