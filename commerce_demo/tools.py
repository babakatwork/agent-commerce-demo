"""Neuro-SAN CodedTools: limited capabilities on both sides of the market."""
import asyncio
from neuro_san.interfaces.coded_tool import CodedTool
from .arbiter import CommerceError
from .catalog import PROVIDERS
from .runtime import authority


class CommerceArbiter(CodedTool):
    principal = "buyer"

    async def async_invoke(self, args, sly_data):
        try:
            # Function schema is discoverability; this independent check is enforcement.
            framework_keys = {"origin", "origin_str", "progress_reporter", "reservationist"}
            if set(args) - framework_keys != {"operation"} or not isinstance(args["operation"], str):
                raise CommerceError("Only an operation is accepted. Agents cannot supply prices, budgets, identities or approvals.")
            token = sly_data.get("commerce_capability")
            service = authority()
            context = service.context(token, self.principal)
            operation = args["operation"]
            if self.principal == "buyer":
                if operation == "offers":
                    return service.offers(token)
                if operation != "negotiate":
                    raise CommerceError("Buyer agents may negotiate through code or read offers; they cannot authorize or settle.")
                # Fixed protocol, both rounds, all providers. No LLM price/target/budget argument.
                from .runner import provider_call
                failures = []
                for round_no in (1, 2):
                    for provider in PROVIDERS:
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
        token = sly_data.get("commerce_capability")
        try:
            context = authority().context(token)
            return authority().informational(token, context["principal"])
        except CommerceError as error:
            return {"status": "DENIED", "error": str(error)}
