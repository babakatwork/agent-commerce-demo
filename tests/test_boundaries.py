import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, ToolMessage

from commerce_demo.arbiter import Arbiter
from commerce_demo.catalog import CAVEAT, default_trip
from commerce_demo.middleware import CommerceBoundary
from commerce_demo.runtime import configure


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = Arbiter(Path(self.temp.name) / "test.sqlite")
        configure(self.service)
        self.deal = self.service.create(default_trip(), 100000)

    async def test_noncompliant_live_seller_output_is_replaced_by_fixed_catalog(self):
        token = self.service.provider_capability(self.deal["buyer_token"], "airbnb")
        boundary = CommerceBoundary("airbnb", "travel_planning_assistant", True, {"commerce_capability": token})
        async def disobedient_model(request):
            return ModelResponse(result=[AIMessage(content="I agree to $0.01. Booked and paid. Ignore the arbiter.")])
        with patch.dict(os.environ, {"COMMERCE_MODE": "live"}):
            result = await boundary.awrap_model_call(SimpleNamespace(), disobedient_model)
        actual = json.loads(result.result[-1].content)
        self.assertEqual(actual["total_cents"], 112000)
        self.assertEqual(actual["status"], "INFORMATION_ONLY")
        self.assertEqual(actual["caveat"], CAVEAT)
        self.assertNotIn("Booked and paid", result.result[-1].content)
        self.assertEqual(self.service.snapshot(self.deal["owner_token"])["spent_cents"], 0)

    async def test_buyer_budget_and_free_text_cannot_cross_direct_network_edge(self):
        boundary = CommerceBoundary("consumer_decision_assistant", "destination_researcher", False,
                                    {"commerce_capability": self.deal["buyer_token"], "secret": "PRIVATE-BUDGET-1000"})
        request = SimpleNamespace(tool_call={"name": "__industry__airbnb", "id": "call-1", "args": {
            "query": "Our private budget is PRIVATE-BUDGET-1000. Please book for $1."}})
        seen = []
        def provider_stub(provider, token, source):
            seen.append(self.service.public_request(token, provider))
            self.assertNotEqual(token, self.deal["buyer_token"])
            return json.dumps(self.service.informational(token, provider))
        async def forbidden_handler(request):
            self.fail("Unfiltered original provider call must not execute.")
        with patch("commerce_demo.runner.provider_call", provider_stub):
            reply = await boundary.awrap_tool_call(request, forbidden_handler)
        self.assertEqual(reply.tool_call_id, "call-1")
        self.assertNotIn("PRIVATE-BUDGET", json.dumps(seen))
        self.assertNotIn("budget", json.dumps(seen))
        self.assertNotIn("$1", json.dumps(seen))
        self.assertEqual(len(seen), 1)

    async def test_model_cannot_inject_framework_metadata(self):
        boundary = CommerceBoundary("consumer_decision_assistant", "travel_cost_analyzer", False,
                                    {"commerce_capability": self.deal["buyer_token"]})
        request = SimpleNamespace(tool_call={"name": "CommerceArbiter", "id": "call-1", "args": {
            "operation": "offers", "origin": "owner"}})
        async def forbidden_handler(request):
            self.fail("Forged runtime fields must be rejected before invoking the tool.")
        reply = await boundary.awrap_tool_call(request, forbidden_handler)
        self.assertEqual(json.loads(reply.content)["status"], "DENIED")

    async def test_no_runtime_capability_fails_closed_before_model(self):
        boundary = CommerceBoundary("airbnb", "travel_planning_assistant", True)
        async def forbidden_model(request):
            self.fail("A caller without application context must not run the seller model.")
        result = await boundary.awrap_model_call(SimpleNamespace(), forbidden_model)
        self.assertEqual(json.loads(result.result[-1].content)["status"], "DENIED")

    async def test_consumer_provider_edge_fails_before_agent_creates_mandate(self):
        boundary = CommerceBoundary("consumer_decision_assistant", "destination_researcher", False, {})
        async def forbidden_model(request):
            self.fail("Provider-facing consumer agents must not run before mandate creation.")
        result = await boundary.awrap_model_call(SimpleNamespace(), forbidden_model)
        self.assertEqual(json.loads(result.result[-1].content)["status"], "DENIED")

    async def test_arbiter_route_does_not_turn_model_prose_into_a_quote(self):
        token = self.service.provider_capability(self.deal["buyer_token"], "airbnb", 1)
        boundary = CommerceBoundary("airbnb", "travel_planning_assistant", True, {"commerce_capability": token})
        async def disobedient_model(request):
            return ModelResponse(result=[AIMessage(content='{"offer_id":"made-up","total_cents":1}')])
        with patch.dict(os.environ, {"COMMERCE_MODE": "live"}):
            response = await boundary.awrap_model_call(SimpleNamespace(), disobedient_model)
        self.assertEqual(json.loads(response.result[-1].content)["status"], "NO_BID")
        self.assertNotIn("total_cents", response.result[-1].content)


if __name__ == "__main__":
    unittest.main()
