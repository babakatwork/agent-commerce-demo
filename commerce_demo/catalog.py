"""Trusted demonstration inventory and seller policies. All amounts are USD cents."""

from datetime import date, timedelta

CAVEAT = (
    "Informational, fixed, non-negotiable catalogue price; no reservation or payment. "
    "Prices may change. Better prices might be available when negotiation and the "
    "transaction are completed through the arbiter."
)
PROVIDERS = ("airbnb", "expedia", "booking")
CONNECTED = (*PROVIDERS, "macys", "carmax", "LinkedInJobSeekerSupportNetwork")
SCOPE = "Two nights for two adults, parking, Wi-Fi and one local activity. Meals and travel to Santa Cruz excluded."
CATALOG = {
    "airbnb": {
        "item_id": "sc-coastal-cottage", "title": "Coastal cottage + kayak outing",
        "list_cents": 112000, "round_one_cents": 104000, "floor_cents": 96000,
        "lodging_cents": 82000, "fees_cents": 18000, "activity_cents": 12000,
        "cancellation": "Full refund until 72 hours before arrival.",
    },
    "expedia": {
        "item_id": "sc-harbor-weekend", "title": "Harbor hotel + coastal bike tour",
        "list_cents": 108000, "round_one_cents": 100000, "floor_cents": 92500,
        "lodging_cents": 80000, "fees_cents": 16000, "activity_cents": 12000,
        "cancellation": "Full refund until 48 hours before arrival.",
    },
    "booking": {
        "item_id": "sc-boardwalk-break", "title": "Boardwalk hotel + aquarium visit",
        "list_cents": 105000, "round_one_cents": 98000, "floor_cents": 91000,
        "lodging_cents": 79000, "fees_cents": 16000, "activity_cents": 10000,
        "cancellation": "Full refund until 24 hours before arrival.",
    },
}


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


def public_catalog(provider, trip):
    if provider not in CATALOG:
        return {
            "provider": provider, "status": "INFORMATION_ONLY", "simulation": True,
            "message": "This copied network is available for advisory discussion; no transaction inventory is configured for it.",
            "caveat": CAVEAT, "offers": [],
        }
    item = CATALOG[provider]
    return {
        "provider": provider, "status": "INFORMATION_ONLY", "simulation": True,
        "item_id": item["item_id"], "title": item["title"], "trip": trip,
        "currency": "USD", "total_cents": item["list_cents"], "scope": SCOPE,
        "cancellation": item["cancellation"], "caveat": CAVEAT,
    }
