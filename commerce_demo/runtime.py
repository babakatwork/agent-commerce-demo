"""Trusted host state for agent-created, policy-bounded mandates."""
import os
import secrets
import threading
from pathlib import Path
from .arbiter import Arbiter
from .catalog import default_retail_purchase, default_trip, validate_retail_purchase, validate_trip

ROOT = Path(__file__).resolve().parent.parent
_arbiter = None
_lock = threading.RLock()
_pending = {}
_controls = {}
_requests = {}
_sessions = {}


def configure(arbiter):
    global _arbiter
    with _lock:
        _arbiter = arbiter
        _pending.clear()
        _controls.clear()
        _requests.clear()
        _sessions.clear()


def authority():
    global _arbiter
    if _arbiter is None:
        _arbiter = Arbiter(os.environ.get("COMMERCE_DB", str(ROOT / ".runtime" / "commerce.sqlite")))
    return _arbiter


def prepare_mandate(trip, ceiling_cents):
    """Register a host policy; the agent still decides when to create the mandate."""
    trip = validate_trip(trip)
    if type(ceiling_cents) is not int or not 1 <= ceiling_cents <= 10_000_000:
        raise ValueError("Mandate ceiling must be a positive integer amount in cents.")
    request_id = secrets.token_urlsafe(24)
    with _lock:
        _pending[request_id] = {"kind": "travel", "trip": trip, "ceiling_cents": ceiling_cents}
    return request_id


def prepare_retail_mandate(purchase, ceiling_cents):
    purchase = validate_retail_purchase(purchase)
    if type(ceiling_cents) is not int or not 1 <= ceiling_cents <= 10_000_000:
        raise ValueError("Mandate ceiling must be a positive integer amount in cents.")
    request_id = secrets.token_urlsafe(24)
    with _lock:
        _pending[request_id] = {"kind": "retail", "purchase": purchase, "ceiling_cents": ceiling_cents}
    return request_id


def mandate_policy(sly_data):
    """Return the trusted policy for this request, or the fixed local nsFlow policy."""
    request_id = sly_data.get("commerce_request_id") if isinstance(sly_data, dict) else None
    with _lock:
        policy = _pending.get(request_id)
    if policy is not None and policy["kind"] == "travel":
        return {"trip": dict(policy["trip"]), "ceiling_cents": policy["ceiling_cents"]}
    # Bare nsFlow is an explicitly local simulation. Its policy is fixed by code,
    # not inferred from model prose, and cannot exceed the configured demo ceiling.
    ceiling = int(os.environ.get("COMMERCE_AGENT_MANDATE_CEILING_CENTS", "100000"))
    return {"trip": default_trip(), "ceiling_cents": ceiling}


def retail_mandate_policy(sly_data):
    request_id = sly_data.get("commerce_request_id") if isinstance(sly_data, dict) else None
    with _lock:
        policy = _pending.get(request_id)
    if policy is not None and policy["kind"] == "retail":
        return {"purchase": dict(policy["purchase"]), "ceiling_cents": policy["ceiling_cents"]}
    ceiling = int(os.environ.get("COMMERCE_RETAIL_MANDATE_CEILING_CENTS", "3000000"))
    return {"purchase": default_retail_purchase(), "ceiling_cents": ceiling}


def register_agent_mandate(sly_data, deal):
    """Bind bearer capabilities to this in-process agent session."""
    deal_id = deal["deal_id"]
    request_id = sly_data.get("commerce_request_id") if isinstance(sly_data, dict) else None
    with _lock:
        _controls[deal_id] = dict(deal)
        _sessions[id(sly_data)] = deal_id
        if request_id:
            _requests[request_id] = deal_id
            _pending.pop(request_id, None)
    # This is display/audit metadata, not an authorization handle.
    sly_data["commerce_deal_id"] = deal_id
    sly_data["commerce_domain"] = authority().context(deal["buyer_token"], "buyer")["kind"]
    return deal_id


def capability(sly_data, principal):
    """Resolve a capability without placing agent-created bearer tokens in sly_data."""
    if not isinstance(sly_data, dict):
        return None
    explicit = sly_data.get("commerce_capability")
    if explicit is not None:
        return explicit
    if principal != "buyer":
        return None
    with _lock:
        deal_id = _sessions.get(id(sly_data))
        control = _controls.get(deal_id)
    return control.get("buyer_token") if control else None


def control_for_request(request_id):
    with _lock:
        handle = _requests.get(request_id)
        control = _controls.get(handle)
    return dict(control) if control else None
