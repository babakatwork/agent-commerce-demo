import asyncio
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from commerce_demo.arbiter import Arbiter, CommerceError
from commerce_demo.catalog import CAVEAT, PROVIDERS, RETAIL_PROVIDERS, default_retail_purchase, default_trip
from commerce_demo.runtime import capability, configure, prepare_mandate, prepare_retail_mandate
from commerce_demo.tools import (
    AirbnbCommerce, CommerceArbiter, RetailMandateAuthority, TravelMandateAuthority,
)


class ArbiterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1800000000.0
        self.service = Arbiter(Path(self.temp.name) / "test.sqlite", clock=lambda: self.now)
        configure(self.service)
        self.deal = self.service.create(default_trip(), 100000)
        self.buyer = self.deal["buyer_token"]
        self.owner = self.deal["owner_token"]

    def quote(self, provider="airbnb"):
        token = self.service.provider_capability(self.buyer, provider, 1)
        return self.service.quote(token, provider)

    def market(self):
        for provider in PROVIDERS:
            self.quote(provider)
        return self.service.resolve(self.buyer)["offers"]

    def test_direct_is_fixed_caveated_and_cannot_quote(self):
        token = self.service.provider_capability(self.buyer, "airbnb")
        info = self.service.informational(token, "airbnb")
        self.assertEqual(info["total_cents"], 112000)
        self.assertEqual(info["caveat"], CAVEAT)
        with self.assertRaises(CommerceError):
            self.service.quote(token, "airbnb")
        self.assertEqual(self.service.snapshot(self.owner)["spent_cents"], 0)

    def test_sealed_bids_resolve_to_equal_weight_nash_compromises(self):
        offers = self.market()
        self.assertEqual([offer["total_cents"] for offer in offers], [95500, 96250, 98000])
        for offer in offers:
            self.assertEqual(sum(item["cents"] for item in offer["line_items"]), offer["total_cents"])
            self.assertEqual(offer["round"], 1)
            self.assertEqual(offer["mechanism"]["name"], "weighted_nash_bargaining")
            self.assertNotIn("floor", json.dumps(offer))
            self.assertNotIn("budget", json.dumps(offer))
        small = self.service.create(default_trip(), 90000)
        for provider in PROVIDERS:
            token = self.service.provider_capability(small["buyer_token"], provider, 1)
            receipt = self.service.submit_bid(token, provider)
            self.assertEqual(receipt["status"], "BID_COMMITTED")
            self.assertNotIn("total_cents", receipt)
        result = self.service.resolve(small["buyer_token"])
        self.assertEqual(result["resolution"], "NO_AGREEMENT")
        self.assertEqual(result["offers"], [])
        no_agreement = next(event for event in self.service.snapshot(small["owner_token"])["events"]
                            if event["kind"] == "NO_AGREEMENT")
        self.assertNotIn("floor", json.dumps(no_agreement))
        self.assertNotIn("budget", json.dumps(no_agreement))

    def test_private_budget_and_other_bids_never_in_seller_view(self):
        self.market()
        token = self.service.provider_capability(self.buyer, "airbnb", 1)
        for view in (self.service.context(token, "airbnb"), self.service.public_request(token, "airbnb")):
            text = json.dumps(view)
            self.assertNotIn("budget", text)
            self.assertNotIn("owner_token", text)
            self.assertNotIn("expedia", text)
        with self.assertRaises(CommerceError):
            self.service.offers(token)

    def test_no_budget_or_identity_or_amount_arguments_to_coded_tool(self):
        tool = AirbnbCommerce()
        token = self.service.provider_capability(self.buyer, "airbnb", 1)
        for extra in ({"amount": 1}, {"budget": 1000}, {"principal": "owner"}, {"approved": True}):
            args = {"operation": "quote", **extra}
            result = asyncio.run(tool.async_invoke(args, {"commerce_capability": token}))
            self.assertEqual(result["status"], "DENIED")
        self.assertEqual(self.service.offers(self.buyer)["offers"], [])

    def test_coded_tool_cannot_authorize_or_settle(self):
        self.market()
        for operation in ("settle", "accept", "authorize", "confirm", "change_budget"):
            result = asyncio.run(CommerceArbiter().async_invoke({"operation": operation}, {"commerce_capability": self.buyer}))
            self.assertEqual(result["status"], "DENIED")
        self.assertEqual(self.service.snapshot(self.owner)["state"], "NEGOTIATING")

    def test_forged_missing_cross_actor_capabilities_fail(self):
        for token in (None, "fabricated", self.owner, self.buyer):
            result = asyncio.run(AirbnbCommerce().async_invoke({"operation": "quote"}, {"commerce_capability": token}))
            self.assertEqual(result["status"], "DENIED")
        token = self.service.provider_capability(self.buyer, "booking", 1)
        with self.assertRaises(CommerceError):
            self.service.quote(token, "airbnb")

    def test_owner_authorization_is_bound_to_deal_and_offer(self):
        offers = self.market()
        foreign = self.service.create(default_trip(), 100000)
        with self.assertRaises(CommerceError):
            self.service.authorize(foreign["owner_token"], offers[0]["offer_id"])
        with self.assertRaises(CommerceError):
            self.service.authorize(self.buyer, offers[0]["offer_id"])

    def test_hold_then_settle_once_even_when_retried(self):
        offer = self.market()[0]
        held = self.service.authorize(self.owner, offer["offer_id"])
        self.assertEqual(held["state"], "HELD")
        self.assertEqual(self.service.snapshot(self.owner)["spent_cents"], 0)
        receipt = self.service.confirm(self.owner)
        self.assertEqual(self.service.confirm(self.owner), receipt)
        self.assertEqual(receipt["paid_cents"], 95500)
        self.assertEqual(self.service.snapshot(self.owner)["hold_cents"], 0)
        with self.service.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ledger").fetchone()[0], 1)

    def test_conflicting_concurrent_accepts_settle_only_one_package(self):
        offers = self.market()
        def attempt(offer):
            try:
                return self.service.authorize(self.owner, offer["offer_id"])
            except CommerceError:
                return None
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(attempt, offers))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.service.confirm(self.owner)
        self.assertLessEqual(self.service.snapshot(self.owner)["spent_cents"], 100000)

    def test_provider_failure_releases_hold(self):
        offer = self.market()[0]
        self.service.authorize(self.owner, offer["offer_id"])
        self.assertEqual(self.service.confirm(self.owner, inventory_available=False)["state"], "CANCELLED")
        state = self.service.snapshot(self.owner)
        self.assertEqual((state["hold_cents"], state["spent_cents"]), (0, 0))

    def test_cancelled_hold_cannot_be_confirmed_later(self):
        offer = self.market()[0]
        self.service.authorize(self.owner, offer["offer_id"])
        self.assertEqual(self.service.snapshot(self.owner)["selected_offer_id"], offer["offer_id"])
        self.assertEqual(self.service.cancel(self.owner)["state"], "CANCELLED")
        self.assertEqual(self.service.confirm(self.owner)["state"], "CANCELLED")
        self.assertEqual(self.service.snapshot(self.owner)["spent_cents"], 0)
        self.assertEqual(self.service.snapshot(self.owner)["hold_cents"], 0)

    def test_expiry_prevents_charge_and_releases_hold(self):
        offer = self.market()[0]
        self.service.authorize(self.owner, offer["offer_id"])
        self.now += 121
        self.assertEqual(self.service.confirm(self.owner)["state"], "EXPIRED")
        self.assertEqual(self.service.snapshot(self.owner)["hold_cents"], 0)

    def test_expired_offer_cannot_be_authorized(self):
        offer = self.market()[0]
        self.now += 901
        self.assertEqual(self.service.offers(self.buyer)["offers"], [])
        with self.assertRaises(CommerceError):
            self.service.authorize(self.owner, offer["offer_id"])

    def test_bid_retries_keep_one_commitment_and_resolution_is_idempotent(self):
        first = self.quote()
        self.now += 10
        self.assertEqual(self.quote(), first)
        first_offers = self.service.resolve(self.buyer)["offers"]
        self.assertEqual(self.service.resolve(self.buyer)["offers"], first_offers)
        events = self.service.snapshot(self.owner)["events"]
        self.assertEqual(sum(event["kind"] == "BID_COMMITTED" for event in events), 1)
        self.assertEqual(sum(event["kind"] == "OFFER_REGISTERED" for event in events), 1)

    def test_only_one_sealed_bid_round_is_allowed(self):
        with self.assertRaises(CommerceError):
            self.service.provider_capability(self.buyer, "airbnb", 2)

    def test_bid_receipt_has_no_offer_authority_before_resolution(self):
        bid = self.quote()
        self.assertEqual(bid["status"], "BID_COMMITTED")
        self.assertEqual(self.service.offers(self.buyer)["offers"], [])
        with self.assertRaises(CommerceError):
            self.service.authorize(self.owner, bid["commitment"])

    def test_persistence_keeps_receipt_and_authorization(self):
        offer = self.market()[0]
        self.service.authorize(self.owner, offer["offer_id"])
        receipt = self.service.confirm(self.owner)
        recovered = Arbiter(self.service.path, clock=lambda: self.now)
        self.assertEqual(recovered.confirm(self.owner), receipt)

    def test_public_requirements_cannot_smuggle_budget_in_free_text(self):
        for changes in ({"notes": "budget 1000"}, {"destination": "Santa Cruz budget 1000"},
                        {"amenities": ["wifi", "secret-1000"]}, {"travelers": True}):
            with self.assertRaises(ValueError):
                self.service.create({**default_trip(), **changes}, 100000)

    def test_nontravel_networks_fail_closed_for_transactions(self):
        for provider in ("macys", "carmax", "LinkedInJobSeekerSupportNetwork"):
            token = self.service.provider_capability(self.buyer, provider)
            self.assertEqual(self.service.informational(token, provider)["status"], "INFORMATION_ONLY")
            with self.assertRaises(CommerceError):
                self.service.quote(token, provider)

    def test_retail_mandate_negotiates_macys_and_carmax_only_through_arbiter(self):
        retail = self.service.create_retail(default_retail_purchase(), 3000000)
        direct_prices = []
        for provider in RETAIL_PROVIDERS:
            direct = self.service.provider_capability(retail["buyer_token"], provider)
            info = self.service.informational(direct, provider)
            direct_prices.append(info["total_cents"])
            self.assertEqual(info["caveat"], CAVEAT)
            with self.assertRaises(CommerceError):
                self.service.quote(direct, provider)
        self.assertEqual(direct_prices, [45000, 2500000])
        for provider in RETAIL_PROVIDERS:
            token = self.service.provider_capability(retail["buyer_token"], provider, 1)
            public = self.service.public_request(token, provider)
            self.assertNotIn("budget", json.dumps(public))
            self.service.submit_bid(token, provider)
        offers = self.service.resolve(retail["buyer_token"])["offers"]
        self.assertEqual([offer["total_cents"] for offer in offers], [42000, 2425000])
        self.assertTrue(all(sum(line["cents"] for line in offer["line_items"]) ==
                            offer["total_cents"] for offer in offers))
        with self.assertRaises(CommerceError):
            self.service.provider_capability(retail["buyer_token"], "airbnb", 1)

    def test_agent_creates_policy_bounded_mandate_without_exposing_capabilities(self):
        trip = default_trip()
        request_id = prepare_mandate(trip, 100000)
        sly_data = {"commerce_request_id": request_id}
        result = asyncio.run(TravelMandateAuthority().async_invoke(
            {**trip, "budget_cents": 95000}, sly_data))
        self.assertEqual(result["status"], "MANDATE_CREATED")
        self.assertEqual(result["created_by"], "travel_decision_specialist")
        self.assertEqual(result["budget"], "PRIVATE")
        self.assertNotIn("commerce_capability", sly_data)
        self.assertNotIn("owner_token", json.dumps(result))
        buyer = capability(sly_data, "buyer")
        self.assertIsInstance(buyer, str)
        self.assertEqual(self.service.context(buyer, "buyer")["deal_id"], result["deal_id"])
        self.assertIsNone(capability({"commerce_deal_id": result["deal_id"]}, "buyer"))

    def test_agent_mandate_cannot_exceed_host_policy_or_change_trip(self):
        trip = default_trip()
        for args in (
            {**trip, "budget_cents": 100001},
            {**trip, "destination": "Paris", "budget_cents": 100000},
        ):
            request_id = prepare_mandate(trip, 100000)
            result = asyncio.run(TravelMandateAuthority().async_invoke(
                args, {"commerce_request_id": request_id}))
            self.assertEqual(result["status"], "DENIED")

    def test_arbiter_connected_agents_cannot_modify_an_issued_mandate(self):
        before = self.service.snapshot(self.owner)
        buyer_data = {"commerce_capability": self.buyer}
        for args in (
            {"operation": "modify_mandate"},
            {"operation": "negotiate", "budget_cents": 1},
            {"operation": "offers", "destination": "San Diego"},
        ):
            result = asyncio.run(CommerceArbiter().async_invoke(args, buyer_data))
            self.assertEqual(result["status"], "DENIED")
        seller = self.service.provider_capability(self.buyer, "airbnb", 1)
        seller_result = asyncio.run(AirbnbCommerce().async_invoke(
            {"operation": "modify_mandate"}, {"commerce_capability": seller}))
        self.assertEqual(seller_result["status"], "DENIED")
        after = self.service.snapshot(self.owner)
        self.assertEqual(after["trip"], before["trip"])
        self.assertEqual(after["budget_cents"], before["budget_cents"])

    def test_database_rejects_mandate_mutation_after_creation(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.service.db() as db:
                db.execute("UPDATE deals SET budget=1 WHERE id=?", (self.deal["deal_id"],))
        snapshot = self.service.snapshot(self.owner)
        self.assertEqual(snapshot["budget_cents"], 100000)
        self.assertEqual(snapshot["trip"], default_trip())

    def test_retail_specialist_creates_bounded_mandate_without_capability_leak(self):
        purchase = default_retail_purchase()
        request_id = prepare_retail_mandate(purchase, 3000000)
        sly_data = {"commerce_request_id": request_id}
        result = asyncio.run(RetailMandateAuthority().async_invoke(
            {**purchase, "budget_cents": 2900000}, sly_data))
        self.assertEqual(result["status"], "MANDATE_CREATED")
        self.assertEqual(result["created_by"], "retail_decision_specialist")
        self.assertNotIn("commerce_capability", sly_data)
        self.assertNotIn("owner_token", json.dumps(result))
        context = self.service.context(capability(sly_data, "buyer"), "buyer")
        self.assertEqual(context["kind"], "retail")
        denied = asyncio.run(RetailMandateAuthority().async_invoke(
            {**purchase, "budget_cents": 3000001},
            {"commerce_request_id": prepare_retail_mandate(purchase, 3000000)},
        ))
        self.assertEqual(denied["status"], "DENIED")


if __name__ == "__main__":
    unittest.main()
