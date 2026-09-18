"""The sole transaction authority. No model output is a price, permission, or receipt.

The Python host and this database are trusted. LLMs can call only the separately
exposed coded-tool methods. This single-process demo is not an OS security sandbox.
"""

import hashlib
import json
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .catalog import (
    CATALOG, CONNECTED, RETAIL_SCOPE, SCOPE, providers_for, public_catalog,
    validate_retail_purchase, validate_trip,
)


class CommerceError(ValueError):
    pass


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class Arbiter:
    def __init__(self, path, clock=time.time):
        self.path = str(path)
        self.clock = clock
        self.lock = threading.RLock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS deals (
                    id TEXT PRIMARY KEY, trip TEXT NOT NULL, budget INTEGER NOT NULL,
                    state TEXT NOT NULL, selected TEXT, hold INTEGER NOT NULL DEFAULT 0,
                    hold_until REAL, spent INTEGER NOT NULL DEFAULT 0, receipt TEXT,
                    created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS capabilities (
                    digest TEXT PRIMARY KEY, deal TEXT NOT NULL, principal TEXT NOT NULL,
                    route TEXT NOT NULL, round INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS offers (
                    id TEXT PRIMARY KEY, deal TEXT NOT NULL, provider TEXT NOT NULL,
                    round INTEGER NOT NULL, amount INTEGER NOT NULL, body TEXT NOT NULL,
                    expires REAL NOT NULL, UNIQUE(deal, provider, round));
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, deal TEXT NOT NULL,
                    kind TEXT NOT NULL, payload TEXT NOT NULL, at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS ledger (
                    id TEXT PRIMARY KEY, deal TEXT NOT NULL, provider TEXT NOT NULL,
                    amount INTEGER NOT NULL, reservation TEXT NOT NULL);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(deals)")}
            if "kind" not in columns:
                db.execute("ALTER TABLE deals ADD COLUMN kind TEXT NOT NULL DEFAULT 'travel'")

    @contextmanager
    def db(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    def _event(self, db, deal, kind, payload):
        db.execute("INSERT INTO events(deal,kind,payload,at) VALUES(?,?,?,?)",
                   (deal, kind, encode(payload), self.clock()))

    def _mint(self, db, deal, principal, route, round_no=0):
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO capabilities VALUES(?,?,?,?,?)",
                   (hashlib.sha256(token.encode()).hexdigest(), deal, principal, route, round_no))
        return token

    def _auth(self, db, token, principal=None):
        if not isinstance(token, str):
            raise CommerceError("Missing runtime capability.")
        cap = db.execute("SELECT * FROM capabilities WHERE digest=?",
                         (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if cap is None or (principal is not None and cap["principal"] != principal):
            raise CommerceError("Capability does not authorize this actor.")
        return cap

    def _deal(self, db, deal_id):
        deal = db.execute("SELECT * FROM deals WHERE id=?", (deal_id,)).fetchone()
        if deal is None:
            raise CommerceError("Unknown deal.")
        return deal

    def _create(self, subject, budget_cents, kind, created_by):
        if type(budget_cents) is not int or not 1 <= budget_cents <= 10000000:
            raise CommerceError("Budget must be a positive integer amount in cents.")
        with self.db() as db:
            deal = secrets.token_hex(12)
            db.execute("INSERT INTO deals(id,trip,budget,state,created,kind) VALUES(?,?,?,?,?,?)",
                       (deal, encode(subject), budget_cents, "OPEN", self.clock(), kind))
            owner = self._mint(db, deal, "owner", "control")
            buyer = self._mint(db, deal, "buyer", "buyer")
            self._event(db, deal, "MANDATE_CREATED", {
                "kind": kind, "subject": subject, "budget": "private to arbiter", "created_by": created_by})
        return {"deal_id": deal, "owner_token": owner, "buyer_token": buyer}

    def create(self, trip, budget_cents, created_by="trusted_application"):
        return self._create(validate_trip(trip), budget_cents, "travel", created_by)

    def create_retail(self, purchase, budget_cents, created_by="retail_decision_specialist"):
        return self._create(validate_retail_purchase(purchase), budget_cents, "retail", created_by)

    def context(self, token, principal=None):
        with self.db() as db:
            cap = self._auth(db, token, principal)
            deal = self._deal(db, cap["deal"])
            # Never return budget, owner capability, other providers' quotes or acceptance status to sellers.
            result = {"deal_id": cap["deal"], "principal": cap["principal"],
                      "route": cap["route"], "round": cap["round"], "kind": deal["kind"]}
            result["trip" if deal["kind"] == "travel" else "purchase"] = json.loads(deal["trip"])
            return result

    def provider_capability(self, buyer_token, provider, round_no=0):
        if provider not in CONNECTED or type(round_no) is not int or round_no not in (0, 1, 2):
            raise CommerceError("Invalid provider or negotiation round.")
        with self.db() as db:
            cap = self._auth(db, buyer_token, "buyer")
            deal = self._deal(db, cap["deal"])
            if round_no and provider not in providers_for(deal["kind"]):
                raise CommerceError("Provider is outside this mandate's transaction scope.")
            if round_no and deal["state"] not in ("OPEN", "NEGOTIATING"):
                raise CommerceError("This deal is no longer open for negotiation.")
            if round_no == 2 and db.execute(
                "SELECT 1 FROM offers WHERE deal=? AND provider=? AND round=1", (cap["deal"], provider)
            ).fetchone() is None:
                raise CommerceError("Round one is required before round two.")
            token = self._mint(db, cap["deal"], provider, "direct" if not round_no else "arbiter", round_no)
            if round_no:
                db.execute("UPDATE deals SET state='NEGOTIATING' WHERE id=?", (cap["deal"],))
            return token

    def public_request(self, token, principal):
        context = self.context(token, principal)
        subject_key = "trip" if context["kind"] == "travel" else "purchase"
        request = {subject_key: context[subject_key], "route": context["route"],
                   "scope": SCOPE if context["kind"] == "travel" else RETAIL_SCOPE}
        if context["route"] == "arbiter":
            request.update({"round": context["round"], "request": "Submit the deterministic provider quote through CommerceArbiter."})
            if context["round"] == 2:
                # Public-list-price-based counter, independent of the buyer's private budget.
                request["target_cents"] = CATALOG[principal]["list_cents"] * 85 // 100
        else:
            request["request"] = "Discuss the package and provide the fixed informational catalogue price."
        return request

    def record_exchange(self, provider_token, source, stage, payload):
        with self.db() as db:
            cap = self._auth(db, provider_token)
            if cap["principal"] not in CONNECTED:
                raise CommerceError("Expected a provider capability.")
            self._event(db, cap["deal"], stage, {"source": source, "provider": cap["principal"],
                        "route": cap["route"], "round": cap["round"], "message": payload})

    def informational(self, token, provider):
        context = self.context(token, provider)
        subject_key = "trip" if context["kind"] == "travel" else "purchase"
        return public_catalog(provider, context[subject_key], context["kind"])

    def quote(self, token, provider):
        with self.db() as db:
            cap = self._auth(db, token, provider)
            deal = self._deal(db, cap["deal"])
            if provider not in providers_for(deal["kind"]) or cap["route"] != "arbiter" or cap["round"] not in (1, 2):
                raise CommerceError("Direct conversations cannot negotiate or issue binding offers. Use the arbiter.")
            if deal["state"] not in ("OPEN", "NEGOTIATING"):
                raise CommerceError("This deal is no longer negotiating.")
            previous = db.execute("SELECT body FROM offers WHERE deal=? AND provider=? AND round=?",
                                  (cap["deal"], provider, cap["round"])).fetchone()
            if previous:
                return json.loads(previous["body"])
            item = CATALOG[provider]
            amount = item["round_one_cents"] if cap["round"] == 1 else max(
                item["floor_cents"], item["list_cents"] * 85 // 100)
            offer_id = secrets.token_hex(16)
            expires = self.clock() + 900
            if deal["kind"] == "travel":
                line_items = [
                    {"label": "Two nights, parking and Wi-Fi", "cents": item["lodging_cents"]},
                    {"label": "Taxes and fees", "cents": item["fees_cents"]},
                    {"label": "Local activity for two", "cents": item["activity_cents"]},
                ]
            else:
                line_items = [{"label": item["title"], "cents": item["list_cents"]}]
            line_items.append({"label": "Arbiter-negotiated discount", "cents": amount - item["list_cents"]})
            body = {
                "offer_id": offer_id, "provider": provider, "item_id": item["item_id"],
                "title": item["title"], "round": cap["round"], "currency": "USD",
                "total_cents": amount, "list_cents": item["list_cents"],
                "savings_cents": item["list_cents"] - amount,
                "line_items": line_items,
                "trip" if deal["kind"] == "travel" else "purchase": json.loads(deal["trip"]),
                "scope": SCOPE if deal["kind"] == "travel" else RETAIL_SCOPE,
                "cancellation": item["cancellation"], "expires_at": expires,
                "simulation": True, "status": "OFFER_ONLY",
            }
            db.execute("INSERT INTO offers VALUES(?,?,?,?,?,?,?)",
                       (offer_id, cap["deal"], provider, cap["round"], amount, encode(body), expires))
            self._event(db, cap["deal"], "OFFER_REGISTERED", body)
            return body

    def offers(self, buyer_token):
        with self.db() as db:
            cap = self._auth(db, buyer_token)
            if cap["principal"] not in ("buyer", "owner"):
                raise CommerceError("Providers cannot read the consumer's shortlist.")
            deal = self._deal(db, cap["deal"])
            # An expired newer quote never revives an older quote.
            rows = db.execute("""SELECT o.* FROM offers o WHERE deal=? AND round=(
                SELECT MAX(round) FROM offers x WHERE x.deal=o.deal AND x.provider=o.provider)
                ORDER BY amount,provider""", (cap["deal"],)).fetchall()
            offers = [json.loads(row["body"]) for row in rows
                      if row["amount"] <= deal["budget"] and row["expires"] > self.clock()]
            return {"state": deal["state"], "offers": offers, "simulation": True,
                    "message": "Select one offer to authorize simulated settlement." if offers
                    else "No unexpired offer meets the private budget. Nothing has been booked."}

    def _expire_hold(self, db, deal):
        if deal["state"] == "HELD" and deal["hold_until"] <= self.clock():
            db.execute("UPDATE deals SET state='EXPIRED',hold=0 WHERE id=?", (deal["id"],))
            self._event(db, deal["id"], "HOLD_RELEASED", {"reason": "confirmation deadline expired"})
            return self._deal(db, deal["id"])
        return deal

    def authorize(self, owner_token, offer_id):
        with self.db() as db:
            cap = self._auth(db, owner_token, "owner")
            deal = self._expire_hold(db, self._deal(db, cap["deal"]))
            if deal["selected"] == offer_id and deal["state"] in ("HELD", "SETTLED"):
                return {"state": deal["state"], "offer_id": offer_id}
            if deal["state"] not in ("OPEN", "NEGOTIATING"):
                raise CommerceError("A deal can authorize only one offer.")
            offer = db.execute("SELECT * FROM offers WHERE id=? AND deal=?", (offer_id, cap["deal"])).fetchone()
            if offer is None or offer["expires"] <= self.clock():
                raise CommerceError("Unknown or expired offer.")
            latest = db.execute("SELECT MAX(round) FROM offers WHERE deal=? AND provider=?",
                                (cap["deal"], offer["provider"])).fetchone()[0]
            if offer["round"] != latest or offer["amount"] > deal["budget"]:
                raise CommerceError("Offer was superseded or exceeds the mandate.")
            db.execute("UPDATE deals SET state='HELD',selected=?,hold=?,hold_until=? WHERE id=?",
                       (offer_id, offer["amount"], self.clock() + 120, cap["deal"]))
            self._event(db, cap["deal"], "FUNDS_HELD", {"offer_id": offer_id, "amount_cents": offer["amount"]})
            return {"state": "HELD", "offer_id": offer_id}

    def confirm(self, owner_token, inventory_available=True):
        """Trusted mock inventory adapter callback; deliberately absent from agent tool schemas."""
        with self.db() as db:
            cap = self._auth(db, owner_token, "owner")
            deal = self._expire_hold(db, self._deal(db, cap["deal"]))
            if deal["state"] == "SETTLED":
                return json.loads(deal["receipt"])
            if deal["state"] != "HELD":
                return {"state": deal["state"], "message": "No active hold to settle."}
            if not inventory_available:
                db.execute("UPDATE deals SET state='CANCELLED',hold=0 WHERE id=?", (cap["deal"],))
                self._event(db, cap["deal"], "HOLD_RELEASED", {"reason": "provider inventory confirmation failed"})
                return {"state": "CANCELLED", "spent_cents": 0}
            offer = db.execute("SELECT * FROM offers WHERE id=?", (deal["selected"],)).fetchone()
            reservation = "SIM-" + secrets.token_hex(6).upper()
            receipt = {"state": "SETTLED", "offer_id": offer["id"], "provider": offer["provider"],
                       "paid_cents": offer["amount"], "currency": "USD", "reservation": reservation,
                       "simulation": True}
            db.execute("INSERT INTO ledger VALUES(?,?,?,?,?)",
                       (deal["id"], deal["id"], offer["provider"], offer["amount"], reservation))
            db.execute("UPDATE deals SET state='SETTLED',spent=?,hold=0,receipt=? WHERE id=?",
                       (offer["amount"], encode(receipt), deal["id"]))
            self._event(db, deal["id"], "PROVIDER_CONFIRMED", {"provider": offer["provider"], "reservation": reservation})
            self._event(db, deal["id"], "SETTLED", receipt)
            return receipt

    def cancel(self, owner_token):
        with self.db() as db:
            cap = self._auth(db, owner_token, "owner")
            deal = self._deal(db, cap["deal"])
            if deal["state"] == "SETTLED":
                raise CommerceError("Settled reservations require a separate refund workflow.")
            if deal["state"] not in ("CANCELLED", "EXPIRED"):
                db.execute("UPDATE deals SET state='CANCELLED',hold=0 WHERE id=?", (deal["id"],))
                self._event(db, deal["id"], "CANCELLED", {"released_cents": deal["hold"]})
            return {"state": "EXPIRED" if deal["state"] == "EXPIRED" else "CANCELLED"}

    def snapshot(self, owner_token):
        with self.db() as db:
            cap = self._auth(db, owner_token, "owner")
            deal = self._expire_hold(db, self._deal(db, cap["deal"]))
            events = [{"seq": row["seq"], "kind": row["kind"], "at": row["at"],
                       "payload": json.loads(row["payload"])} for row in db.execute(
                           "SELECT * FROM events WHERE deal=? ORDER BY seq", (deal["id"],))]
            result = {"deal_id": deal["id"], "kind": deal["kind"], "budget_cents": deal["budget"],
                    "state": deal["state"], "hold_cents": deal["hold"], "spent_cents": deal["spent"],
                    "selected_offer_id": deal["selected"],
                    "receipt": json.loads(deal["receipt"]) if deal["receipt"] else None, "events": events}
            result["trip" if deal["kind"] == "travel" else "purchase"] = json.loads(deal["trip"])
            return result
