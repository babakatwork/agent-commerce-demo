"""Real Neuro-SAN graph execution in process, including external network calls."""
import json
import os
from .arbiter import encode
from .runtime import ROOT, authority


def setup(mode="replay"):
    from neuro_san_studio.commands.project_environment import ProjectEnvironment
    os.environ["COMMERCE_MODE"] = mode
    os.environ["AGENT_MANIFEST_FILE"] = str(ROOT / "registries" / ("live/manifest.hocon" if mode == "live" else "manifest.hocon"))
    os.environ["AGENT_TOOL_PATH"] = str(ROOT / "coded_tools")
    os.environ["AGENT_TOOLBOX_INFO_FILE"] = str(ROOT / "config" / "toolbox.hocon")
    ProjectEnvironment(ROOT).apply()


def call_network(network, text, token):
    from neuro_san.client.agent_session_factory import AgentSessionFactory
    session = AgentSessionFactory().create_session("direct", f"industry/{network}", use_direct=True)
    messages = []
    try:
        request = {"user_message": {"text": text}, "sly_data": {"commerce_capability": token}}
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
    result = call_network(provider, encode(public), seller_token)
    service.record_exchange(seller_token, source, "A2A_RESPONSE", json.loads(result))
    return result


def run_consumer(buyer_token):
    # Budget stays in the private application form/database, absent from all model contexts.
    trip = authority().context(buyer_token, "buyer")["trip"]
    return json.loads(call_network("consumer_decision_assistant", encode({"request": "Find Santa Cruz vacation options and use the arbiter to negotiate offers.", "trip": trip}), buyer_token))
