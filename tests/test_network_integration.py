import tempfile
import unittest
import json
from pathlib import Path

from commerce_demo.arbiter import Arbiter
from commerce_demo.catalog import CAVEAT, default_trip
from commerce_demo.runner import call_network, run_consumer, run_retail, setup
from commerce_demo.runtime import configure
from commerce_demo.validation import validate


class NetworkIntegrationTests(unittest.TestCase):
    def test_copied_networks_keep_all_prompts_and_original_connections(self):
        result = validate()
        self.assertEqual(result["networks"], 7)
        self.assertEqual(result["original_prompt_changes"], 0)
        self.assertEqual(result["original_edges_removed"], 0)

    def test_actual_neuro_san_graph_runs_a2a_market_and_settlement(self):
        with tempfile.TemporaryDirectory() as temp:
            service = Arbiter(Path(temp) / "integration.sqlite")
            configure(service)
            setup("replay")
            result, deal = run_consumer(default_trip(), 100000)
            self.assertEqual([o["total_cents"] for o in result["offers"]], [95500, 96250, 98000])
            snapshot = service.snapshot(deal["owner_token"])
            events = snapshot["events"]
            mandate = next(e for e in events if e["kind"] == "MANDATE_CREATED")
            self.assertEqual(mandate["payload"]["created_by"], "travel_decision_specialist")
            requests = [e for e in events if e["kind"] == "A2A_REQUEST"]
            self.assertEqual(len(requests), 6)
            self.assertEqual(sum(e["payload"]["route"] == "direct" for e in requests), 3)
            self.assertTrue(all("budget" not in str(e["payload"]["message"]) for e in requests))
            self.assertEqual(sum(e["kind"] == "BID_COMMITTED" for e in events), 3)
            self.assertEqual(sum(e["kind"] == "OFFER_REGISTERED" for e in events), 3)
            self.assertEqual(sum(e["kind"] == "BARGAINING_RESOLVED" for e in events), 1)
            direct = [e["payload"]["message"] for e in events if e["kind"] == "A2A_RESPONSE" and e["payload"]["route"] == "direct"]
            self.assertEqual([d["total_cents"] for d in direct], [112000, 108000, 105000])
            self.assertTrue(all(d["caveat"] == CAVEAT for d in direct))
            self.assertEqual(snapshot["spent_cents"], 0)
            service.authorize(deal["owner_token"], result["offers"][0]["offer_id"])
            receipt = service.confirm(deal["owner_token"])
            self.assertEqual(receipt["state"], "SETTLED")
            self.assertEqual(receipt["paid_cents"], 95500)

    def test_bare_nsflow_style_call_needs_no_precreated_mandate(self):
        with tempfile.TemporaryDirectory() as temp:
            service = Arbiter(Path(temp) / "nsflow.sqlite")
            configure(service)
            setup("replay")
            result = json.loads(call_network(
                "consumer_decision_assistant",
                "Book a Santa Cruz weekend within a $1000 maximum; negotiate but do not settle.",
                {},
            ))
            self.assertEqual([o["total_cents"] for o in result["offers"]], [95500, 96250, 98000])
            with service.db() as db:
                event = db.execute(
                    "SELECT payload FROM events WHERE kind='MANDATE_CREATED' ORDER BY seq DESC LIMIT 1"
                ).fetchone()
            self.assertEqual(json.loads(event["payload"])["created_by"], "travel_decision_specialist")

    def test_retail_agents_use_arbiter_for_macys_and_carmax(self):
        with tempfile.TemporaryDirectory() as temp:
            service = Arbiter(Path(temp) / "retail.sqlite")
            configure(service)
            setup("replay")
            result, deal = run_retail()
            self.assertEqual([offer["provider"] for offer in result["offers"]], ["macys", "carmax"])
            self.assertEqual([offer["total_cents"] for offer in result["offers"]], [42000, 2425000])
            snapshot = service.snapshot(deal["owner_token"])
            self.assertEqual(snapshot["kind"], "retail")
            mandate = next(event for event in snapshot["events"] if event["kind"] == "MANDATE_CREATED")
            self.assertEqual(mandate["payload"]["created_by"], "retail_decision_specialist")
            requests = [event["payload"] for event in snapshot["events"] if event["kind"] == "A2A_REQUEST"]
            self.assertEqual(len(requests), 6)
            self.assertEqual(sum(request["route"] == "direct" for request in requests), 4)
            self.assertTrue(all("budget" not in json.dumps(request["message"]) for request in requests))
            tool_agents = {event["payload"]["agent"] for event in snapshot["events"]
                           if event["kind"] == "TOOL_RESULT"}
            self.assertTrue({"product_researcher", "price_comparison_agent"} <= tool_agents)

    def test_bare_nsflow_retail_prompt_routes_without_manual_sly_data(self):
        with tempfile.TemporaryDirectory() as temp:
            service = Arbiter(Path(temp) / "retail-nsflow.sqlite")
            configure(service)
            setup("replay")
            result = json.loads(call_network(
                "consumer_decision_assistant",
                "Use Macy's and CarMax to research a retail purchase through the arbiter.",
                {},
            ))
            self.assertEqual([offer["provider"] for offer in result["offers"]], ["macys", "carmax"])
            self.assertEqual([offer["total_cents"] for offer in result["offers"]], [42000, 2425000])


if __name__ == "__main__":
    unittest.main()
