# Agent commerce demo

A standalone overlay project depending on `neuro-san-studio`. It preserves the
consumer network and all six connected B2C networks. Direct conversations return
fixed informational catalogue prices. The arbiter alone computes negotiated
offers and records simulated settlement. The original agent instruction strings
are unchanged.

```bash
uv sync
uv run commerce-demo validate
uv run commerce-demo demo --settle
uv run commerce-demo serve
```

Open http://127.0.0.1:8765 for the guided demonstration. Default mode is explicitly
**scripted replay**: real Neuro-SAN graphs, tools and middleware execute, with
scripted model decisions and fixture inventory. No API key or web search needed.

For a real model, set `OPENAI_API_KEY` in your shell and run
`uv run commerce-demo serve --mode live`. The protected networks use
`gpt-4.1-mini`; edit only the `llm_config` in the generated live HOCON files to
use another model. The price, privacy and transaction controls are identical.

Use the project directory as your working directory. The editable source checkout
is the supported installation; the copied registry files live next to the Python
package. `uv.lock` fixes the complete dependency set, independently of the parent
consultant project. No parent networks or prompts were edited.

## A five-minute demo

1. Start `uv run commerce-demo serve` and open the local page. Leave the $1,000
   private limit and the explicit Friday–Sunday dates, then click **Find &
   negotiate packages**.
2. The original consumer hierarchy runs: `decision_consultant` →
   `travel_decision_specialist` → `destination_researcher` / `travel_cost_analyzer`.
   The researcher talks directly to all three provider networks. Their fixed
   catalogue prices are Airbnb $1,120, Expedia $1,080 and Booking.com $1,050.
3. The cost analyzer calls its `CommerceArbiter` coded tool. It opens two bounded
   rounds with the actual provider networks. Each provider calls its own
   principal-bound arbiter tool to register its offer. The final prices are
   **$960, $925 and $910**. No model supplies any of these numbers.
4. Click **Try a bypass**. A direct provider conversation still works and retains
   its original catalogue price and caveat. A seller-supplied $0.01 override and a
   buyer's attempted `settle` operation both return `DENIED`.
5. Choose a package using **Select & hold funds**. The private application creates
   the hold. Click **Confirm inventory & settle** to simulate the trusted inventory
   adapter callback and release the held funds. A receipt appears. The alternative
   **Simulate inventory failure** releases the hold without a charge.

Expand audit entries to inspect exactly what each provider received. There is no
budget in those requests. The downloadable audit is a consumer/admin view and
does include the private mandate; it is never sent to provider agents.

For an unsuccessful search, start a fresh deal with a $900 limit: no eligible
package is returned. Prices offered by sellers remain the same regardless of
the buyer's limit. No extra negotiation rounds reveal a budget threshold.

The fixtures cover two nights for two adults, parking, Wi-Fi and one local
activity. Meals and transport to Santa Cruz are explicitly excluded. Dates and
requirements are validated by code. Fixtures are illustrative, not live availability.

## Where enforcement lives

| Boundary | Enforcement |
| --- | --- |
| Private budget | Structured consumer form → SQLite; absent from all model prompts, tool schemas and provider contexts. |
| Direct A2A requests | `CommerceBoundary` invokes the destination network with an approved public trip request and a new provider-scoped capability. Model-written free text and parent `sly_data` do not cross this edge. |
| Direct A2A responses | Provider frontman middleware returns the canonical catalogue response with fixed prices and the mandatory caveat, even if the LLM claims to negotiate or book. |
| Seller identity | Separate provider coded-tool classes and database-issued capabilities bound to one deal, provider, route and round. Identity is never taken from model arguments. |
| Negotiated prices | Trusted provider policies in `catalog.py`. Round one uses the published demo policy; round two counters at 85% of catalogue, subject to each supplier's private floor. The target is independent of the buyer's limit. |
| Offers | Arbiter-issued opaque IDs reference immutable records containing exact trip, terms, price and expiry. An LLM-authored offer ID or price has no authority. |
| Purchase authority | Only the consumer application holds the owner capability. Agents have `negotiate`/`offers` or `catalog`/`quote`; no agent has an authorization or settlement operation. |
| Settlement | Owner approval → 120-second simulated hold → trusted inventory confirmation → one atomic SQLite ledger entry and receipt. Failure or expiry releases funds. |
| Repetition/concurrency | Unique `(deal, provider, round)` quotes and one ledger row per deal. Retried quotes do not extend expiry; concurrent conflicting approvals cannot buy several alternatives. |

The direct-response caveat is rendered by code, not by a prompt:

> Informational, fixed, non-negotiable catalogue price; no reservation or payment.
> Prices may change. Better prices might be available when negotiation and the
> transaction are completed through the arbiter.

The original A2A **connections and instruction strings** are preserved, but the
messages crossing the provider boundary are constrained. Completely unrestricted
free-text A2A would be incompatible with a hard no-budget-disclosure guarantee.
Internal agent discussion still follows the original graph. Web search is replaced
by a local fixture tool so it cannot become an uncontrolled outbound channel.

## Files and network copies

- `commerce_demo/arbiter.py`: database, capabilities, offers, state machine and ledger.
- `commerce_demo/tools.py`: buyer and provider `CodedTool` adapters.
- `commerce_demo/middleware.py`: public-message boundary, canonical responses and
  the clearly labelled scripted model decisions used only in replay mode.
- `commerce_demo/runner.py`: genuine Neuro-SAN direct sessions, including calls to
  the copied external provider networks. Middleware uses a fresh session per
  external call to avoid sharing the buyer's private context with a provider.
- `commerce_demo/server.py` and `static/`: local consumer application and audit view.
- `registries/industry/`: executable replay copies of the consumer, Airbnb,
  Expedia, Booking.com, Macy's, CarMax and LinkedIn networks.
- `registries/live/industry/`: equivalent networks configured for a live LLM.
- `upstream/`: exact source snapshots, copyright notices and SHA-256 provenance.
- `scripts/build_networks.py`: reproducible mechanical overlay; it adds tool
  descriptions and middleware, without editing any original `instructions` field.

All six B2C networks have the arbiter adapter. Transaction inventory is implemented
for the three travel providers. Macy's, CarMax and LinkedIn fail closed for
transactions and report that no transaction inventory is configured; their source
graphs are retained for later domain adapters. This is a travel demo, not an
implementation of checkout for all six businesses.

Regenerate both modes and verify prompt/connection preservation:

```bash
uv run python scripts/build_networks.py
uv run commerce-demo validate
uv run python -m unittest discover -s tests -v
```

The tests include a full Neuro-SAN replay (nine provider exchanges and six offers),
noncompliant-model response injection against the live-mode middleware, budget
leak attempts, forged identities, unauthorized settlement, expiry, failure,
concurrent approvals, retries, persistence and unchanged prompts/connections.
The real-model path requires credentials; the replay does not prove the quality
or consistency of live LLM orchestration.

## Operating boundaries

This is a **single-process local simulation**. The Python host, registry
configuration, provider policy adapters and database are trusted. It protects
against an LLM using its exposed tools incorrectly; it is not a sandbox against
malicious Python plugins, an administrator editing SQLite, or arbitrary code
execution. Database events are append-only by application convention, not a
cryptographically tamper-evident audit trail.

The UI binds to loopback and requires a session cookie, same-origin requests and
a CSRF token for changes. Owner credentials stay on the server. Start through
`commerce-demo`, which creates and scopes the required runtime capabilities.
Calling these networks in a bare `ns run`/nsflow session without that application
context deliberately returns `DENIED`.

Offers expire after 15 minutes. Hold expiry is processed when state is read or
confirmation is attempted; there is no background payment processor. Browser
sessions are in memory, so a server restart requires a new browser demo session.
The ledger and capabilities remain in SQLite; unit tests verify receipt recovery
through the trusted backend. Simulated funds are scoped to each mandate rather
than a shared banking wallet. Cancellation after settlement/refunds are outside
this demo's scope.

To use independent third-party services later, place the arbiter behind an
authenticated API, replace local capabilities with authenticated service
identities, and replace fixture pricing/inventory/payment callbacks with trusted
provider integrations. Preserve the same operation restrictions and state
transitions. Real provider reservations and payment capture require reconciliation
for partial failures; a SQLite transaction alone cannot make remote services atomic.
