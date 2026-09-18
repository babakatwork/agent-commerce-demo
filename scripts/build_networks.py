"""Mechanical overlay of seven copied networks. Original instructions are preserved exactly."""
import hashlib
import json
from pathlib import Path
from pyhocon import ConfigFactory

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "upstream"
PROVIDERS = {
    "airbnb": "AirbnbCommerce", "expedia": "ExpediaCommerce", "booking": "BookingCommerce",
    "macys": "MacysCommerce", "carmax": "CarmaxCommerce", "LinkedInJobSeekerSupportNetwork": "LinkedInCommerce",
}


def build():
    manifest, live_manifest, provenance = {}, {}, {}
    for network in ("consumer_decision_assistant", *PROVIDERS):
        source = SOURCE / "registries" / "industry" / f"{network}.hocon"
        raw = source.read_text()
        data = ConfigFactory.parse_string(raw, basedir=str(SOURCE)).as_plain_ordered_dict()
        original = {agent["name"]: agent.get("instructions") for agent in data["tools"]}
        buyer = network == "consumer_decision_assistant"
        for index, agent in enumerate(data["tools"]):
            if "toolbox" in agent:
                agent.pop("toolbox")
                agent["class"] = "commerce_demo.tools.FixtureSearch"
                agent["function"] = {"description": "Read the offline demonstration catalogue.", "parameters": {
                    "type": "object", "properties": {"query": {"type": "string"}}, "required": []}}
                continue
            agent["middleware"] = [{"class": "commerce_demo.middleware.CommerceBoundary", "args": {
                "network": network, "agent": agent["name"], "frontman": index == 0, "sly_data": True}}]
            # Outbound calls are mediated explicitly; no parent's private dictionary is forwarded.
            agent["allow"] = {"to_downstream": {"sly_data": False}, "to_upstream": {"sly_data": False}}
            if buyer and agent["name"] == "travel_decision_specialist":
                # This agent has no provider edge. It creates the bounded mandate
                # before delegating research to agents that do contact providers.
                agent.setdefault("tools", []).append("TravelMandateAuthority")
            if buyer and agent["name"] == "retail_decision_specialist":
                # Like its travel peer, this specialist has no provider edge and
                # creates the bounded mandate before downstream market activity.
                agent.setdefault("tools", []).append("RetailMandateAuthority")
            if (buyer and agent["name"] in (
                    "travel_cost_analyzer", "product_researcher", "price_comparison_agent")) or (
                    not buyer and index == 0):
                agent.setdefault("tools", []).append("CommerceArbiter")
        if buyer:
            data["tools"].append({
                "name": "TravelMandateAuthority", "class": "commerce_demo.tools.TravelMandateAuthority",
                "function": {
                    "description": "Create the private, code-bounded travel mandate before delegating provider research. "
                                   "Only the travel_decision_specialist has this tool. Call it once with the user's "
                                   "structured trip and maximum budget; code rejects anything outside the trusted scope.",
                    "parameters": {"type": "object", "additionalProperties": False,
                        "properties": {
                            "destination": {"type": "string"},
                            "arrival": {"type": "string", "description": "YYYY-MM-DD"},
                            "departure": {"type": "string", "description": "YYYY-MM-DD"},
                            "travelers": {"type": "integer"},
                            "amenities": {"type": "array", "items": {"type": "string"}},
                            "budget_cents": {"type": "integer"}},
                        "required": ["destination", "arrival", "departure", "travelers", "amenities", "budget_cents"]}}})
            data["tools"].append({
                "name": "RetailMandateAuthority", "class": "commerce_demo.tools.RetailMandateAuthority",
                "function": {
                    "description": "Create a private, code-bounded retail mandate before Macy's or CarMax research. "
                                   "Only retail_decision_specialist has this tool; code enforces the trusted scope.",
                    "parameters": {"type": "object", "additionalProperties": False,
                        "properties": {
                            "query": {"type": "string"},
                            "providers": {"type": "array", "items": {"type": "string"}},
                            "quantity": {"type": "integer"},
                            "budget_cents": {"type": "integer"}},
                        "required": ["query", "providers", "quantity", "budget_cents"]}}})
        operations = ["negotiate", "offers"] if buyer else ["catalog", "quote"]
        data["tools"].append({
            "name": "CommerceArbiter", "class": "commerce_demo.tools." + ("CommerceArbiter" if buyer else PROVIDERS[network]),
            "function": {"description": "Mandatory coded authority for negotiated prices. Direct discussions are informational. "
                         + ("Use negotiate to consult the providers in the coded travel or retail mandate, then offers to read the shortlist. Settlement requires the consumer application." if buyer
                            else "Use catalog for direct inquiries; quote for arbiter-routed requests. Code sets all prices."),
                         "parameters": {"type": "object", "additionalProperties": False,
                                        "properties": {"operation": {"type": "string", "enum": operations}},
                                        "required": ["operation"]}}})
        data["max_steps"] = 100
        data["max_execution_seconds"] = 180
        data["llm_config"] = {"class": "commerce_demo.replay_model.ReplayModel"}
        # JSON is valid HOCON. Semantic prompt equality is checked instead of noisy formatting diffs.
        target = ROOT / "registries" / "industry" / f"{network}.hocon"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Derived from Cognizant neuro-san-studio; see upstream/ and NOTICE.\n" + json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        manifest[f"industry/{network}.hocon"] = True
        data["llm_config"] = {"model_name": "gpt-4.1-mini"}
        live = ROOT / "registries" / "live" / "industry" / f"{network}.hocon"
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_text("# Same protected network with a live LLM; see NOTICE.\n" + json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        live_manifest[f"industry/{network}.hocon"] = True
        assert all(agent.get("instructions") == original[agent["name"]] for agent in data["tools"] if agent["name"] in original)
        provenance[network] = {"sha256": hashlib.sha256(raw.encode()).hexdigest(), "original_prompt_count": len(original), "prompt_changes": 0}
    (ROOT / "registries" / "manifest.hocon").write_text(json.dumps(manifest, indent=2) + "\n")
    # Manifest base directory must be the live directory to keep external names /industry/… identical.
    (ROOT / "registries" / "live" / "manifest.hocon").write_text(json.dumps(live_manifest, indent=2) + "\n")
    (ROOT / "upstream" / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Generated {len(manifest)} protected networks in replay and live modes; zero original prompt edits.")


if __name__ == "__main__":
    build()
