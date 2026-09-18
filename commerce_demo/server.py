"""Loopback-only demo application. Owner authority never enters an agent context."""
import asyncio
import json
import secrets
import threading
from datetime import date, timedelta
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files

from .arbiter import CommerceError
from .catalog import CAVEAT, default_trip
from .runtime import authority


def make_handler(mode="replay"):
    sessions = {}
    lock = threading.RLock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, cookie=None):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if cookie:
                self.send_header("Set-Cookie", f"commerce_session={cookie}; HttpOnly; SameSite=Strict; Path=/")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def session(self):
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            value = cookie.get("commerce_session")
            key = value.value if value else ""
            return sessions.get(key)

        def check_host(self):
            return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

        def do_GET(self):
            if not self.check_host():
                return self.reply(403, {"error": "Local host required."})
            if self.path == "/api/bootstrap":
                with lock:
                    session = self.session()
                    key = None
                    if session is None:
                        key = secrets.token_urlsafe(32)
                        session = {"csrf": secrets.token_urlsafe(32), "deal": None, "busy": False, "error": None, "bypass": None}
                        sessions[key] = session
                return self.reply(200, {"csrf": session["csrf"], "mode": mode, "trip": default_trip(), "caveat": CAVEAT}, key)
            if self.path == "/api/state":
                with lock:
                    session = self.session()
                    if session is None:
                        return self.reply(401, {"error": "Start a browser session."})
                    deal = session["deal"]
                    result = {"busy": session["busy"], "error": session["error"], "bypass": session["bypass"], "mode": mode}
                    if deal:
                        result.update(authority().snapshot(deal["owner_token"]))
                        market = authority().offers(deal["owner_token"])
                        result.update({key: value for key, value in market.items() if key != "deal_id"})
                return self.reply(200, result)
            assets = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
            if self.path not in assets:
                return self.reply(404, {"error": "Not found."})
            data = files("commerce_demo").joinpath("static", assets[self.path]).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", {"/": "text/html; charset=utf-8", "/app.js": "text/javascript", "/style.css": "text/css"}[self.path])
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if not self.check_host() or self.headers.get("Origin", "") not in (
                f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"
            ):
                return self.reply(403, {"error": "Same-origin requests required."})
            with lock:
                session = self.session()
                if session is None or not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf"]):
                    return self.reply(403, {"error": "Consumer session authorization required."})
                if session["busy"]:
                    return self.reply(409, {"error": "The current network run is still in progress."})
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 8192 or self.headers.get("Content-Type") != "application/json":
                        raise ValueError("Expected a small JSON request.")
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict):
                        raise ValueError("Expected an object.")
                    if self.path == "/api/start":
                        if set(body) != {"budget_cents", "arrival"}:
                            raise ValueError("Expected budget_cents and arrival.")
                        if session["deal"]:
                            old = authority().snapshot(session["deal"]["owner_token"])
                            if old["state"] == "HELD":
                                raise ValueError("Cancel or confirm the active hold before starting again.")
                        arrival = date.fromisoformat(body["arrival"])
                        trip = {**default_trip(), "arrival": arrival.isoformat(), "departure": (arrival + timedelta(days=2)).isoformat()}
                        session["deal"] = None
                        session.update({"busy": True, "error": None, "bypass": None})
                        threading.Thread(target=self.run_job, args=(session, trip, body["budget_cents"]), daemon=True).start()
                        return self.reply(202, {"status": "RUNNING"})
                    if not session["deal"]:
                        raise ValueError("Start the demonstration first.")
                    owner = session["deal"]["owner_token"]
                    if self.path == "/api/authorize":
                        if set(body) != {"offer_id"} or not isinstance(body["offer_id"], str):
                            raise ValueError("Select an exact offer.")
                        return self.reply(200, authority().authorize(owner, body["offer_id"]))
                    if self.path == "/api/confirm":
                        if set(body) != {"inventory_available"} or type(body["inventory_available"]) is not bool:
                            raise ValueError("Choose a simulated provider confirmation outcome.")
                        return self.reply(200, authority().confirm(owner, body["inventory_available"]))
                    if self.path == "/api/cancel":
                        if body:
                            raise ValueError("No arguments expected.")
                        return self.reply(200, authority().cancel(owner))
                    if self.path == "/api/bypass":
                        if body:
                            raise ValueError("No arguments expected.")
                        session["busy"] = True
                        threading.Thread(target=self.bypass_job, args=(session,), daemon=True).start()
                        return self.reply(202, {"status": "RUNNING"})
                    return self.reply(404, {"error": "Not found."})
                except (ValueError, TypeError, KeyError) as error:
                    return self.reply(400, {"error": str(error)})

        def run_job(self, session, trip, budget_cents):
            try:
                from .runner import run_consumer
                _, deal = run_consumer(trip, budget_cents)
                with lock:
                    session["deal"] = deal
                state = authority().snapshot(session["deal"]["owner_token"])
                if not any(event["kind"] in ("BARGAINING_RESOLVED", "NO_AGREEMENT")
                           for event in state["events"]):
                    raise CommerceError("The networks did not resolve bargaining. Check live model configuration or use replay mode.")
            except Exception as error:
                with lock:
                    session["error"] = f"{type(error).__name__}: {error}"
            finally:
                with lock:
                    session["busy"] = False

        def bypass_job(self, session):
            try:
                from .runner import provider_call
                from .tools import AirbnbCommerce, CommerceArbiter
                buyer = session["deal"]["buyer_token"]
                token = authority().provider_capability(buyer, "airbnb")
                direct = json.loads(provider_call("airbnb", token, "bypass demonstration"))
                price_attack = asyncio.run(AirbnbCommerce().async_invoke(
                    {"operation": "quote", "amount_cents": 1}, {"commerce_capability": token}))
                settlement_attack = asyncio.run(CommerceArbiter().async_invoke(
                    {"operation": "settle"}, {"commerce_capability": buyer}))
                with lock:
                    session["bypass"] = {"direct": direct, "price_attack": price_attack, "settlement_attack": settlement_attack}
                authority().record_exchange(token, "bypass demonstration", "BYPASS_DENIED", {
                    "direct_price_cents": direct["total_cents"], "agent_price_override": price_attack["status"],
                    "agent_settlement": settlement_attack["status"]})
            except Exception as error:
                with lock:
                    session["error"] = f"{type(error).__name__}: {error}"
            finally:
                with lock:
                    session["busy"] = False

    return Handler


def serve(port=8765, mode="replay"):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(mode))
    print(f"Commerce demo: http://127.0.0.1:{server.server_port} — {mode} mode; simulated money and inventory", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
