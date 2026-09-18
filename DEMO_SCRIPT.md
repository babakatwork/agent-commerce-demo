# Demo script

This runbook shows the implementation in nsFlow first, then presents the same
controls through the Common Ground web experience. Allow about eight minutes.

## Prepare

```bash
cd ~/projects/agent-commerce-demo
git pull --ff-only
uv sync --locked
uv run commerce-demo validate
uv run python -m unittest discover -s tests -v
```

## Part 1: show the system in nsFlow

Start nsFlow in the first terminal:

```bash
cd ~/projects/agent-commerce-demo
uv run ns run --server-http-port 8080 --nsflow-port 4173
```

Open it on macOS:

```bash
open http://localhost:4173
```

Select `industry/consumer_decision_assistant`. Leave **Edited Sly Data** empty and
send:

```text
Find a Santa Cruz vacation for the configured weekend with a maximum budget of
$1000. Create the mandate, negotiate through the arbiter, and do not settle.
```

Use the graph and logs for this talk track:

1. `decision_consultant` delegates to `travel_decision_specialist`.
2. `TravelMandateAuthority` creates the mandate. Buyer and owner capabilities
   remain in trusted runtime state rather than SlyData.
3. `destination_researcher` calls Airbnb, Expedia and Booking.com directly. These
   calls return fixed catalogue prices with the mandatory informational caveat.
4. `travel_cost_analyzer` invokes `CommerceArbiter` with only `operation=negotiate`.
5. Each provider agent calls its own coded adapter. The adapter commits a sealed
   policy bid and returns `BID_COMMITTED` with a commitment hash, not a price.
6. After collecting bids, the arbiter applies equal-weight Nash bargaining. It
   registers Booking.com at $955, Expedia at $962.50 and Airbnb at $980.
7. The agent receives the canonical shortlist. It still lacks `authorize` and
   `settle` operations.

Open one provider network and point out its `CommerceArbiter` tool. In the logs,
show that the provider request contains public trip requirements, the mechanism
name and the bid round. It contains neither the buyer ceiling nor competing bids.

Presenter line:

> Agents decide whom to consult and when to invoke the mechanism. Coded policy
> supplies the numbers, and the arbiter alone decides whether the private ranges
> overlap and what compromise follows from the published rule.

## Part 2: show the Common Ground experience

Keep nsFlow open. Start the web demo in a second terminal:

```bash
cd ~/projects/agent-commerce-demo
uv run commerce-demo serve --port 8765
```

Open it:

```bash
open http://127.0.0.1:8765
```

First demonstrate failure safely:

1. Set the private spending ceiling to `$900`.
2. Click **Find & negotiate packages**.
3. Show the fixed direct catalogue responses and the sealed bid commitments in
   the audit.
4. Point out `NO_AGREEMENT`. Every seller floor exceeds the mandate, so the
   arbiter creates no offer and reveals no private value.

Then demonstrate agreement and settlement:

1. Change the ceiling to `$1,000` and run again.
2. Show the three Nash compromise offers: `$955`, `$962.50` and `$980`.
3. Expand `BID_COMMITTED`, `BARGAINING_RESOLVED` and `OFFER_REGISTERED` events.
4. Click **Try a bypass**. The direct price remains informational, a model-supplied
   `$0.01` price fails, and agent settlement fails.
5. Select Booking.com's `$955` offer and place the simulated hold.
6. Click **Confirm inventory & settle** and show the receipt.

Close with:

> Direct agent communication remains useful for discovery. The arbiter turns
> private constraints and sealed provider policy into a deterministic agreement,
> then requires separate owner approval before money can move.

Privacy wording for Q&A: raw budgets and bids never enter the opposing LLM
context. Do not claim that a published final price reveals no economic
information; like any bargaining outcome, it can support some inference.

Stop both services with `Ctrl+C` in their terminals.
