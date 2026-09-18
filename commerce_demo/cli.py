import argparse
import json
import logging
from pathlib import Path

from .arbiter import Arbiter
from .catalog import default_trip
from .runtime import ROOT, configure


def main():
    parser = argparse.ArgumentParser(description="Arbiter-controlled Neuro-SAN commerce demo")
    parser.add_argument("command", choices=["demo", "serve", "validate"], nargs="?", default="demo")
    parser.add_argument("--mode", choices=["replay", "live"], default="replay")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--budget", type=int, default=1000, help="Whole-USD ceiling enforced around the agent proposal")
    parser.add_argument("--db", type=Path, default=ROOT / ".runtime" / "commerce.sqlite")
    parser.add_argument("--settle", action="store_true", help="Explicitly authorize the cheapest eligible simulated package")
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)
    from .runner import setup
    setup(args.mode)
    engine = Arbiter(args.db)
    configure(engine)
    if args.command == "validate":
        from .validation import validate
        print(json.dumps(validate(), indent=2))
    elif args.command == "serve":
        from .server import serve
        serve(args.port, args.mode)
    else:
        from .runner import run_consumer
        print(f"Running actual Neuro-SAN networks in {args.mode} mode. All inventory and money are simulated.", flush=True)
        offers, deal = run_consumer(default_trip(), args.budget * 100)
        print(json.dumps(offers, indent=2), flush=True)
        if args.settle and offers.get("offers"):
            engine.authorize(deal["owner_token"], offers["offers"][0]["offer_id"])
            print(json.dumps(engine.confirm(deal["owner_token"]), indent=2))
        snapshot = engine.snapshot(deal["owner_token"])
        output = ROOT / ".runtime" / "last-demo.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(snapshot, indent=2) + "\n")
        print(f"Audit: {output}")
        expected = 9  # Three direct conversations, then two mediated rounds with three providers.
        requests = [event for event in snapshot["events"] if event["kind"] == "A2A_REQUEST"]
        if len(requests) < expected or len([event for event in snapshot["events"] if event["kind"] == "OFFER_REGISTERED"]) != 6:
            raise RuntimeError("Incomplete market execution; inspect the audit and provider errors.")


if __name__ == "__main__":
    main()
