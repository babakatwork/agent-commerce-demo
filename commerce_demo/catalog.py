"""Trusted demonstration inventory and seller policies. All amounts are USD cents."""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import re

CAVEAT = (
    "Informational, fixed, non-negotiable catalogue price; no reservation or payment. "
    "Prices may change. Better prices might be available when negotiation and the "
    "transaction are completed through the arbiter."
)
PROVIDERS = ("airbnb", "expedia", "booking")
RETAIL_PROVIDERS = ("macys", "carmax")
TRANSACTION_PROVIDERS = (*PROVIDERS, *RETAIL_PROVIDERS)
CONNECTED = (*TRANSACTION_PROVIDERS, "LinkedInJobSeekerSupportNetwork")
SUPPORTED_AMENITIES = {"accessible", "breakfast", "kitchen", "parking", "pet-friendly", "pool", "wifi"}
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
    destination = trip["destination"]
    if (not isinstance(destination, str) or not destination.strip() or len(destination) > 80 or
            re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", destination.strip()) is None):
        raise ValueError("Destination must be a non-empty place name.")
    if type(trip["travelers"]) is not int or not 1 <= trip["travelers"] <= 12:
        raise ValueError("Travelers must be an integer from 1 through 12.")
    if (not isinstance(trip["amenities"], list) or len(trip["amenities"]) > 12 or
            any(not isinstance(value, str) or not value.strip() or len(value) > 40
                for value in trip["amenities"]) or
            any(value not in SUPPORTED_AMENITIES for value in trip["amenities"])):
        raise ValueError("Amenities must use the supported allowlist.")
    arrival, departure = date.fromisoformat(trip["arrival"]), date.fromisoformat(trip["departure"])
    if arrival.isoformat() != trip["arrival"] or departure.isoformat() != trip["departure"]:
        raise ValueError("Dates must use YYYY-MM-DD.")
    if not timedelta(days=1) <= departure - arrival <= timedelta(days=30) or arrival < date.today():
        raise ValueError("Choose 1 to 30 nights with an arrival date today or later.")
    return {**trip, "destination": destination.strip(), "amenities": list(trip["amenities"])}


def parse_travel_request(text, today=None):
    """Deterministically normalize a small, explicit subset of bare nsFlow requests."""
    if not isinstance(text, str):
        raise ValueError("A text travel request is required.")
    today = today or date.today()
    destination_match = re.search(
        r"(?:\b(?:in|to)\s+)([A-Za-z][A-Za-z .'-]{1,79}?)(?=\s+(?:for|during|over|from|with|under|within|on|at|and)\b|[.,;!?]|$)",
        text, re.IGNORECASE,
    )
    if destination_match is None:
        raise ValueError("Please name a destination using 'in' or 'to'.")
    destination = " ".join(destination_match.group(1).split()).title()

    amount_match = re.search(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text)
    if amount_match is None:
        amount_match = re.search(
            r"\bbudget(?:\s+(?:of|is))?\s+([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
            text, re.IGNORECASE,
        )
    if amount_match is None:
        raise ValueError("Please include a maximum budget, for example '$1000'.")
    try:
        ceiling_cents = int(Decimal(amount_match.group(1).replace(",", "")) * 100)
    except (InvalidOperation, ValueError):
        raise ValueError("The budget could not be read.") from None
    if not 1 <= ceiling_cents <= 10_000_000:
        raise ValueError("The budget must be between $0.01 and $100,000.")

    iso_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if len(iso_dates) >= 2:
        arrival, departure = date.fromisoformat(iso_dates[0]), date.fromisoformat(iso_dates[1])
    elif "christmas" in text.lower():
        year = today.year if date(today.year, 12, 24) >= today else today.year + 1
        arrival, departure = date(year, 12, 24), date(year, 12, 26)
    else:
        arrival = today + timedelta(days=7 - today.weekday() + 4)
        departure = arrival + timedelta(days=2)

    travelers_match = re.search(
        r"\b(\d{1,2})\s+(?:adults?|travel(?:l)?ers?|people|persons?|guests?)\b", text, re.IGNORECASE)
    travelers = int(travelers_match.group(1)) if travelers_match else 2
    amenities = []
    lowered = text.lower()
    if "parking" in lowered:
        amenities.append("parking")
    if "wi-fi" in lowered or "wifi" in lowered:
        amenities.append("wifi")
    trip = validate_trip({
        "destination": destination, "arrival": arrival.isoformat(),
        "departure": departure.isoformat(), "travelers": travelers, "amenities": amenities,
    })
    return {"trip": trip, "ceiling_cents": ceiling_cents}


def travel_scope(trip):
    arrival, departure = date.fromisoformat(trip["arrival"]), date.fromisoformat(trip["departure"])
    nights = (departure - arrival).days
    people = f"{trip['travelers']} traveler" + ("" if trip["travelers"] == 1 else "s")
    return (f"{nights} night" + ("" if nights == 1 else "s") +
            f" for {people} in {trip['destination']}. Illustrative fixture inventory; "
            f"meals and travel to {trip['destination']} are excluded.")


def travel_item(provider, trip):
    item = dict(CATALOG[provider])
    if trip["destination"].casefold() != "santa cruz":
        labels = {"airbnb": "Airbnb stay", "expedia": "Expedia hotel package",
                  "booking": "Booking.com stay"}
        slug = re.sub(r"[^a-z0-9]+", "-", trip["destination"].lower()).strip("-")
        item.update({"item_id": f"{provider}-{slug}-demo",
                     "title": f"{labels[provider]} in {trip['destination']}"})
    return item


def public_catalog(provider, subject, kind="travel"):
    if provider not in CATALOG:
        return {
            "provider": provider, "status": "INFORMATION_ONLY", "simulation": True,
            "message": "This copied network is available for advisory discussion; no transaction inventory is configured for it.",
            "caveat": CAVEAT, "offers": [],
        }
    item = travel_item(provider, subject) if kind == "travel" else CATALOG[provider]
    return {
        "provider": provider, "status": "INFORMATION_ONLY", "simulation": True,
        "item_id": item["item_id"], "title": item["title"],
        "trip" if kind == "travel" else "purchase": subject,
        "currency": "USD", "total_cents": item["list_cents"],
        "scope": travel_scope(subject) if kind == "travel" else RETAIL_SCOPE,
        "cancellation": item["cancellation"], "caveat": CAVEAT,
    }
