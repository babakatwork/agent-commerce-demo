"""Neuro-SAN CodedTools: limited capabilities on both sides of the market."""
import asyncio
from .catalog import providers_for, validate_retail_purchase, validate_trip
from neuro_san.interfaces.coded_tool import CodedTool
from .arbiter import CommerceError
from .runtime import (
    authority, capability, mandate_policy, register_agent_mandate, retail_mandate_policy,
)


class TravelMandateAuthority(CodedTool):
    """Agent-invoked issuance constrained by a trusted host policy."""

    async def async_invoke(self, args, sly_data):
        try:
            framework_keys = {"origin", "origin_str", "progress_reporter", "reservationist"}
            supplied = {key: value for key, value in args.items() if key not in framework_keys}
            required = {"destination", "arrival", "departure", "travelers", "amenities", "budget_cents"}
            if set(supplied) != required:
                raise CommerceError("A complete structured trip and budget_cents are required.")
            if not isinstance(sly_data, dict):
                raise CommerceError("Mandate creation requires a runtime session.")
            existing = capability(sly_data, "buyer")
            if existing:
                context = authority().context(existing, "buyer")
                return {"status": "MANDATE_EXISTS", "deal_id": context["deal_id"],
                        "trip": context["trip"], "budget": "PRIVATE", "simulation": True}
            trip = validate_trip({key: supplied[key] for key in required if key != "budget_cents"})
            budget = supplied["budget_cents"]
            policy = mandate_policy(sly_data)
            if trip != policy["trip"]:
                raise CommerceError("The proposed trip is outside the trusted request scope.")
            if type(budget) is not int or not 1 <= budget <= policy["ceiling_cents"]:
                raise CommerceError("The proposed budget exceeds the trusted mandate ceiling.")
            deal = authority().create(trip, budget, created_by="travel_decision_specialist")
            register_agent_mandate(sly_data, deal)
            return {"status": "MANDATE_CREATED", "deal_id": deal["deal_id"], "trip": trip,
                    "budget": "PRIVATE", "created_by": "travel_decision_specialist", "simulation": True}
        except (CommerceError, ValueError) as error:
            return {"error": str(error), "status": "DENIED", "simulation": True}


class RetailMandateAuthority(CodedTool):
    """Agent-invoked retail issuance constrained by trusted host policy."""

    async def async_invoke(self, args, sly_data):
        try:
            framework_keys = {"origin", "origin_str", "progress_reporter", "reservationist"}
            supplied = {key: value for key, value in args.items() if key not in framework_keys}
            required = {"query", "providers", "quantity", "budget_cents"}
            if set(supplied) != required or not isinstance(sly_data, dict):
                raise CommerceError("A complete structured retail request and budget_cents are required.")
            existing = capability(sly_data, "buyer")
            if existing:
                context = authority().context(existing, "buyer")
                return {"status": "MANDATE_EXISTS", "deal_id": context["deal_id"],
                        "kind": context["kind"], "budget": "PRIVATE", "simulation": True}
            purchase = validate_retail_purchase({key: supplied[key] for key in required if key != "budget_cents"})
            budget = supplied["budget_cents"]
            policy = retail_mandate_policy(sly_data)
            if purchase != policy["purchase"]:
                raise CommerceError("The proposed purchase is outside the trusted request scope.")
            if type(budget) is not int or not 1 <= budget <= policy["ceiling_cents"]:
                raise CommerceError("The proposed budget exceeds the trusted retail mandate ceiling.")
            deal = authority().create_retail(purchase, budget, created_by="retail_decision_specialist")
            register_agent_mandate(sly_data, deal)
            return {"status": "MANDATE_CREATED", "deal_id": deal["deal_id"], "purchase": purchase,
                    "budget": "PRIVATE", "created_by": "retail_decision_specialist", "simulation": True}
        except (CommerceError, ValueError) as error:
            return {"error": str(error), "status": "DENIED", "simulation": True}


class CommerceArbiter(CodedTool):
    principal = "buyer"

    async def async_invoke(self, args, sly_data):
        try:
            # Function schema is discoverability; this independent check is enforcement.
            framework_keys = {"origin", "origin_str", "progress_reporter", "reservationist"}
            if set(args) - framework_keys != {"operation"} or not isinstance(args["operation"], str):
                raise CommerceError("Only an operation is accepted. Agents cannot supply prices, budgets, identities or approvals.")
            token = capability(sly_data, self.principal)
            service = authority()
            context = service.context(token, self.principal)
            operation = args["operation"]
            if self.principal == "buyer":
                if operation == "offers":
                    return service.offers(token)
                if operation != "negotiate":
                    raise CommerceError("Buyer agents may negotiate through code or read offers; they cannot authorize or settle.")
                # Fixed protocol, both rounds, providers selected by the coded mandate.
                from .runner import provider_call
                failures = []
                for round_no in (1, 2):
                    for provider in providers_for(context["kind"]):
                        try:
                            seller_token = service.provider_capability(token, provider, round_no)
                            await asyncio.to_thread(provider_call, provider, seller_token, "CommerceArbiter")
                        except Exception as error:
                            # A partial market remains useful; never substitute invented offers.
                            failures.append({"provider": provider, "round": round_no, "error": type(error).__name__})
                result = service.offers(token)
                result["unavailable"] = failures
                return result
            if operation == "catalog":
                return service.informational(token, self.principal)
            if operation == "quote":
                return service.quote(token, self.principal)
            raise CommerceError("Provider agents cannot accept, charge, settle, or modify a price.")
        except CommerceError as error:
            return {"error": str(error), "status": "DENIED", "simulation": True}


class AirbnbCommerce(CommerceArbiter):
    principal = "airbnb"


class ExpediaCommerce(CommerceArbiter):
    principal = "expedia"


class BookingCommerce(CommerceArbiter):
    principal = "booking"


class MacysCommerce(CommerceArbiter):
    principal = "macys"


class CarmaxCommerce(CommerceArbiter):
    principal = "carmax"


class LinkedInCommerce(CommerceArbiter):
    principal = "LinkedInJobSeekerSupportNetwork"


class FixtureSearch(CodedTool):
    """Offline inventory replaces web-search egress in copied provider networks."""
    async def async_invoke(self, args, sly_data):
        # Provider fixture calls always arrive with an explicit provider-scoped token.
        token = capability(sly_data, "buyer")
        try:
            context = authority().context(token)
            return authority().informational(token, context["principal"])
        except CommerceError as error:
            return {"status": "DENIED", "error": str(error)}
