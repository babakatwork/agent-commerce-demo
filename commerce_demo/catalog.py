"""Trusted demonstration inventory and seller policies. All amounts are USD cents."""

from datetime import date, timedelta

CAVEAT = (
    "Informational, fixed, non-negotiable catalogue price; no reservation or payment. "
    "Prices may change. Better prices might be available when negotiation and the "
    "transaction are completed through the arbiter."
)
PROVIDERS = ("airbnb", "expedia", "booking")
RETAIL_PROVIDERS = ("macys", "carmax")
TRANSACTION_PROVIDERS = (*PROVIDERS, *RETAIL_PROVIDERS)
CONNECTED = (*TRANSACTION_PROVIDERS, "LinkedInJobSeekerSupportNetwork")
SCOPE = "Two nights for two adults, parking, Wi-Fi and one local activity. Meals and travel to Santa Cruz excluded."
CATALOG = {
    "airbnb": {
        "item_id": "sc-coastal-cottage", "title": "Coastal cottage + kayak outing",
        "list_cents": 112000, "floor_cents": 96000,
        "lodging_cents": 82000, "fees_cents": 18000, "activity_cents": 12000,
        "cancellation": "Full refund until 72 hours before arrival.",
    },
    "expedia": {
        "item_id": "sc-harbor-weekend", "title": "Harbor hotel + coastal bike tour",
        "list_cents": 108000, "floor_cents": 92500,
        "lodging_cents": 80000, "fees_cents": 16000, "activity_cents": 12000,
        "cancellation": "Full refund until 48 hours before arrival.",
    },
    "booking": {
        "item_id": "sc-boardwalk-break", "title": "Boardwalk hotel + aquarium visit",
        "list_cents": 105000, "floor_cents": 91000,
        "lodging_cents": 79000, "fees_cents": 16000, "activity_cents": 10000,
        "cancellation": "Full refund until 24 hours before arrival.",
    },
    "macys": {
        "item_id": "macys-weekender-set", "title": "Illustrative Macy's weekender luggage set",
        "list_cents": 45000, "floor_cents": 39000,
        "cancellation": "Simulated return permitted within 30 days.",
    },
    "carmax": {
        "item_id": "carmax-corolla-demo", "title": "Illustrative CarMax pre-owned compact car",
        "list_cents": 2500000, "floor_cents": 2350000,
        "cancellation": "Simulated offer subject to vehicle inspection and availability.",
    },
}

RETAIL_SCOPE = "Illustrative retail sourcing request; product details and availability are fixture data, not live inventory."


def validate_retail_purchase(purchase):
    if set(purchase) != {"query", "providers", "quantity"}:
        raise ValueError("Use only query, providers and quantity for a retail mandate.")
    if purchase["query"] != "illustrative retail purchase":
        raise ValueError("The replay fixture supports only its configured retail purchase.")
    if purchase["providers"] != list(RETAIL_PROVIDERS) or purchase["quantity"] != 1:
        raise ValueError("The retail demo is scoped to one item from Macy's or CarMax.")
    return {"query": purchase["query"], "providers": list(purchase["providers"]), "quantity": 1}


def default_retail_purchase():
    return {"query": "illustrative retail purchase", "providers": list(RETAIL_PROVIDERS), "quantity": 1}


def providers_for(kind):
    return PROVIDERS if kind == "travel" else RETAIL_PROVIDERS if kind == "retail" else ()


def default_trip(today=None):
    """Explicit dates: the Friday of the following calendar week, never guessed by an LLM."""
    today = today or date.today()
    arrival = today + timedelta(days=7 - today.weekday() + 4)
    return {
        "destination": "Santa Cruz", "arrival": arrival.isoformat(),
        "departure": (arrival + timedelta(days=2)).isoformat(),
        "travelers": 2, "amenities": ["parking", "wifi"],
    }


def validate_trip(trip):
    if set(trip) != {"destination", "arrival", "departure", "travelers", "amenities"}:
        raise ValueError("Use only the supported public trip fields.")
    if trip["destination"] != "Santa Cruz" or type(trip["travelers"]) is not int or trip["travelers"] != 2:
        raise ValueError("The demonstration inventory is for Santa Cruz and two adults.")
    if trip["amenities"] != ["parking", "wifi"]:
        raise ValueError("Demo packages include parking and Wi-Fi.")
    arrival, departure = date.fromisoformat(trip["arrival"]), date.fromisoformat(trip["departure"])
    if arrival.isoformat() != trip["arrival"] or departure.isoformat() != trip["departure"]:
        raise ValueError("Dates must use YYYY-MM-DD.")
    if departure - arrival != timedelta(days=2) or arrival < date.today():
        raise ValueError("Choose two nights with an arrival date today or later.")
    return dict(trip)


def public_catalog(provider, subject, kind="travel"):
    if provider not in CATALOG:
        return {
            "provider": provider, "status": "INFORMATION_ONLY", "simulation": True,
            "message": "This copied network is available for advisory discussion; no transaction inventory is configured for it.",
            "caveat": CAVEAT, "offers": [],
        }
    item = CATALOG[provider]
    return {
        "provider": provider, "status": "INFORMATION_ONLY", "simulation": True,
        "item_id": item["item_id"], "title": item["title"],
        "trip" if kind == "travel" else "purchase": subject,
        "currency": "USD", "total_cents": item["list_cents"],
        "scope": SCOPE if kind == "travel" else RETAIL_SCOPE,
        "cancellation": item["cancellation"], "caveat": CAVEAT,
    }
