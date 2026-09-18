import tempfile
import unittest
import json
from pathlib import Path

from commerce_demo.arbiter import Arbiter
from commerce_demo.catalog import CAVEAT, default_trip
from commerce_demo.runner import call_network, run_consumer, setup
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
            self.assertEqual([o["total_cents"] for o in result["offers"]], [91000, 92500, 96000])
            snapshot = service.snapshot(deal["owner_token"])
            events = snapshot["events"]
            mandate = next(e for e in events if e["kind"] == "MANDATE_CREATED")
            self.assertEqual(mandate["payload"]["created_by"], "travel_decision_specialist")
            requests = [e for e in events if e["kind"] == "A2A_REQUEST"]
            self.assertEqual(len(requests), 9)
            self.assertEqual(sum(e["payload"]["route"] == "direct" for e in requests), 3)
            self.assertTrue(all("budget" not in str(e["payload"]["message"]) for e in requests))
            self.assertEqual(sum(e["kind"] == "OFFER_REGISTERED" for e in events), 6)
            direct = [e["payload"]["message"] for e in events if e["kind"] == "A2A_RESPONSE" and e["payload"]["route"] == "direct"]
            self.assertEqual([d["total_cents"] for d in direct], [112000, 108000, 105000])
            self.assertTrue(all(d["caveat"] == CAVEAT for d in direct))
            self.assertEqual(snapshot["spent_cents"], 0)
            service.authorize(deal["owner_token"], result["offers"][0]["offer_id"])
            receipt = service.confirm(deal["owner_token"])
            self.assertEqual(receipt["state"], "SETTLED")
            self.assertEqual(receipt["paid_cents"], 91000)

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
            self.assertEqual([o["total_cents"] for o in result["offers"]], [91000, 92500, 96000])
            with service.db() as db:
                event = db.execute(
                    "SELECT payload FROM events WHERE kind='MANDATE_CREATED' ORDER BY seq DESC LIMIT 1"
                ).fetchone()
            self.assertEqual(json.loads(event["payload"])["created_by"], "travel_decision_specialist")


if __name__ == "__main__":
    unittest.main()
