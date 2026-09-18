"""Validate copied graph coverage, guarded edges, and unmodified source instructions."""
from pyhocon import ConfigFactory
from .catalog import CONNECTED
from .runtime import ROOT


def validate():
    counts = {}
    for network in ("consumer_decision_assistant", *CONNECTED):
        original = ConfigFactory.parse_string((ROOT / "upstream/registries/industry" / f"{network}.hocon").read_text(), basedir=str(ROOT / "upstream"))
        for mode_dir in (ROOT / "registries", ROOT / "registries/live"):
            active = ConfigFactory.parse_file(str(mode_dir / "industry" / f"{network}.hocon"))
            by_name = {agent["name"]: agent for agent in active["tools"]}
            for before in original["tools"]:
                after = by_name[before["name"]]
                assert before.get("instructions", None) == after.get("instructions", None), before["name"]
                assert set(before.get("tools", [])) <= set(after.get("tools", [])), before["name"]
                if "instructions" in after:
                    assert after["middleware"][0]["class"] == "commerce_demo.middleware.CommerceBoundary"
                assert "toolbox" not in after, "Uncontrolled web-search egress"
            assert "CommerceArbiter" in by_name
            if network == "consumer_decision_assistant":
                assert "TravelMandateAuthority" in by_name
                self_creator = by_name["travel_decision_specialist"]
                assert "TravelMandateAuthority" in self_creator.get("tools", [])
                assert not set(self_creator.get("tools", [])) & {"/industry/airbnb", "/industry/expedia", "/industry/booking"}
                for name, agent in by_name.items():
                    if name != "travel_decision_specialist":
                        assert "TravelMandateAuthority" not in agent.get("tools", [])
        counts[network] = len(original["tools"])
    return {"networks": len(counts), "original_nodes": counts, "original_prompt_changes": 0,
            "original_edges_removed": 0, "modes": ["replay", "live"]}
