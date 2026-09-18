"""Real Neuro-SAN graph execution in process, including external network calls."""
import json
import os
from .arbiter import encode
from .catalog import default_trip
from .runtime import ROOT, authority, control_for_request, prepare_mandate


def setup(mode="replay"):
    from neuro_san_studio.commands.project_environment import ProjectEnvironment
    os.environ["COMMERCE_MODE"] = mode
    os.environ["AGENT_MANIFEST_FILE"] = str(ROOT / "registries" / ("live/manifest.hocon" if mode == "live" else "manifest.hocon"))
    os.environ["AGENT_TOOL_PATH"] = str(ROOT / "coded_tools")
    os.environ["AGENT_TOOLBOX_INFO_FILE"] = str(ROOT / "config" / "toolbox.hocon")
    ProjectEnvironment(ROOT).apply()


def call_network(network, text, sly_data=None):
    from neuro_san.client.agent_session_factory import AgentSessionFactory
    session = AgentSessionFactory().create_session("direct", f"industry/{network}", use_direct=True)
    messages = []
    try:
        request = {"user_message": {"text": text}, "sly_data": sly_data if sly_data is not None else {}}
        for response in session.streaming_chat(request):
            message = response.get("response", {})
            if message.get("text"):
                messages.append(message["text"])
        # Frontman middleware renders a single canonical JSON response.
        for text in reversed(messages):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and ("status" in parsed or "state" in parsed or "offer_id" in parsed):
                    return encode(parsed)
            except (ValueError, TypeError):
                pass
        raise RuntimeError(f"Network {network} did not return a canonical response; messages={messages[-2:]}")
    finally:
        session.close()


def provider_call(provider, seller_token, source):
    service = authority()
    public = service.public_request(seller_token, provider)
    service.record_exchange(seller_token, source, "A2A_REQUEST", public)
    result = call_network(provider, encode(public), {"commerce_capability": seller_token})
    service.record_exchange(seller_token, source, "A2A_RESPONSE", json.loads(result))
    return result


def run_consumer(trip=None, budget_cents=100000):
    """Let the travel specialist create the mandate, then return its host control."""
    trip = trip or default_trip()
    request_id = prepare_mandate(trip, budget_cents)
    message = encode({
        "request": "Create a bounded mandate, then find Santa Cruz vacation options and use the arbiter to negotiate offers.",
        "trip": trip,
        "maximum_budget_cents": budget_cents,
    })
    result = json.loads(call_network(
        "consumer_decision_assistant", message, {"commerce_request_id": request_id}))
    control = control_for_request(request_id)
    if control is None:
        raise RuntimeError("The travel specialist did not create a mandate.")
    return result, control
