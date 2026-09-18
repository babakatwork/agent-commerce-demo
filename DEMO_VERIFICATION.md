# Verification record

Verified locally on 2026-09-18 with the standalone project's own `uv` environment
and locked dependencies (`neuro-san-studio` 0.3.20, `neuro-san` 0.6.95).

- The seven copied networks preserve all 93 original node definitions' instruction
  strings and every original tool connection. Both replay and live configurations
  pass the comparison against retained source snapshots.
- The CLI executes actual Neuro-SAN graphs with scripted model decisions: three
  direct provider exchanges, then two mediated rounds across all three providers.
- The travel specialist creates the mandate through `TravelMandateAuthority`
  before delegating. It has no direct provider edge; code constrains its proposal
  to the trusted trip and maximum ceiling, and no bearer capability enters SlyData.
- The retail specialist likewise creates a code-bounded mandate without a Macy's
  or CarMax edge. `product_researcher` and `price_comparison_agent` both use
  `CommerceArbiter`; four direct informational calls and four arbiter-routed calls
  execute across the two copied provider networks without disclosing the budget.
- Retail fixture prices are Macy's $450 and CarMax $25,000 informationally, with
  canonical coded offers of $390 and $23,500 after two arbiter rounds.
- Direct prices: Airbnb $1,120; Expedia $1,080; Booking.com $1,050. All include the
  fixed informational/non-negotiable caveat.
- Final coded offers: Airbnb $960; Expedia $925; Booking.com $910. The $1,000
  mandate remains absent from every outgoing provider request.
- A CLI run with `--settle` produced one $910 simulated settlement and a receipt.
- Browser walkthrough: agent creates mandate → see three offers → try bypass → fixed
  Airbnb price unchanged → $0.01 override denied → agent settlement denied →
  consumer selects Booking.com → funds held → confirm → $910 receipt displayed.
- All 34 automated tests cover bare-nsFlow travel and retail mandate creation,
  immutable pricing, scoped identities, direct-route
  restrictions, private-budget isolation, unauthorized purchase attempts,
  expiry, concurrent acceptance, provider failure, cancellation, persistence,
  retries and the real Neuro-SAN graph integration.
- Live-mode middleware was exercised with deliberately noncompliant model stubs;
  fabricated prices, booking claims and fabricated quotes were rejected or
  replaced by canonical coded results.

No paid live LLM call was run: API credentials were not configured in the process.
Use `--mode live` with a configured `OPENAI_API_KEY` to test real model orchestration.
All tested bookings and money movement are simulated.

Reproduce:

```bash
uv sync --locked
uv run commerce-demo validate
uv run python -m unittest discover -s tests -v
uv run commerce-demo demo --settle
uv run commerce-demo serve
# Under the hood: uv run ns run, then open http://localhost:4173
```
