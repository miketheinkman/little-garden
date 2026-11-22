"""Short-lived signaling, scoped by the authorized learner on each endpoint."""
import json
import re

from django.core.cache import caches

LEASE = 8


def token(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def description(value):
    return (isinstance(value, str) and len(value) <= 24576 and value.startswith("v=0")
            and "m=application " in value and "m=audio " not in value and "m=video " not in value)


def object_field(data, key):
    try:
        value = json.loads(data.get(key, "{}"))
    except (ValueError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


def viewer_signal(child_id, source, signal):
    live = caches["coview"]
    peer = signal.get("id")
    matched = token(source) and token(peer) and signal.get("source") == source
    if not matched or signal.get("direct") is not True:
        # A second viewer can need the relay while another is connected directly.
        live.set(f"relay:{child_id}", True, 3)
    if not matched:
        return {}
    prefix = f"rtc:{child_id}:{source}"
    live.set(f"{prefix}:lease:{peer}", True, LEASE)
    answer = live.get(f"{prefix}:answer:{peer}")
    if not answer and description(signal.get("offer")):
        # One short offer slot per learner. Unanswered viewers retry on their next poll.
        live.add(f"{prefix}:offer", {"id": peer, "sdp": signal["offer"]}, 2)
    return {"answer": answer} if answer and signal.get("offer") else {}


def child_signal(child_id, source, data):
    if not token(source):
        return {}
    live = caches["coview"]
    prefix = f"rtc:{child_id}:{source}"
    peers = data.get("peers", "").split(",")[:16]
    allowed = [peer for peer in peers if token(peer) and live.get(f"{prefix}:lease:{peer}")]
    answer = object_field(data, "answer")
    peer = answer.get("id")
    if peer in allowed and description(answer.get("sdp")):
        live.set(f"{prefix}:answer:{peer}", answer["sdp"], LEASE)
    offer = live.get(f"{prefix}:offer")
    if offer and not live.get(f"{prefix}:lease:{offer['id']}"):
        offer = None
    return {"allowed": allowed, "offer": offer, "relay": bool(live.get(f"relay:{child_id}"))}
