# Book Opportunity Scout

Book Opportunity Scout is a local-first Agency agent that proposes coloring-book concepts, attaches structured research evidence, applies deterministic Python scoring, and returns a ranked shortlist for local approval, rejection, or saving for later.

It does not generate interiors or covers, access Amazon KDP, upload or publish books, buy advertising, place orders, or modify marketplace accounts.

## Agency lifecycle

The catalog ID is `jamesos.book-opportunity-scout`. Discover and hire it through The Agency catalog, review its local-write permissions, keep the default local model `qwen3:14b`, and place it On Duty through the existing confirmed Agency enable action. It requires no secrets.

Its Agent OS capabilities are:

- `books.opportunity.research`
- `books.opportunity.decide`

## Demonstration

Open The Agency, select Book Opportunity Scout, and run the default request:

```json
{
  "market": "US",
  "audience": "children ages 4-8",
  "book_type": "coloring book",
  "candidate_count": 20,
  "result_count": 5
}
```

Research Mode supports `demo`, `manual`, and `live`. DEMO returns twenty reproducible candidates and a stable top five from labeled fixture evidence. MANUAL accepts normalized structured evidence. LIVE composes replaceable, public read-only adapters for Amazon search visibility, public web results, a freely accessible trend signal, and publicly visible review snippets. Amazon challenge pages stop collection and are reported as blocked; no CAPTCHA bypass is attempted. Amazon visibility is never described as verified sales volume.

Live retrieval uses HTTPS GET requests without accounts or credentials, conservative throttling, ten-second timeouts, at most two attempts, a six-hour local cache, and a two-megabyte response bound. Partial runs retain missing/failed/blocked evidence and lower confidence rather than inventing values. The UI discloses attempted, completed and blocked sources, evidence count, cache age, missing metrics, confidence, and collection warnings.

## Evidence and scoring

Every evidence record includes its source, concept, metric, raw and normalized values, timestamp, confidence, status, reference, summary, and safe error details. Missing metrics remain unavailable, contribute zero points, reduce confidence, and appear in the result.

The default profile totals 100 points: demand 25, competition opportunity 20, purchase intent 15, differentiation 10, seasonal timing 10, profitability 10, production simplicity 5, and series potential 5. Python calculates the score; an LLM cannot alter it. High-risk franchise, celebrity, logo, or medical-claim concepts are withheld from the recommended top five for manual review.

## Local storage

Private run artifacts are stored under the JamesOS data root at the logical path:

```text
JamesOS/Books/OpportunityScout/runs/<run-id>/
```

Each run contains the request, candidates, evidence, scoring profile, results, and a local HTML report. Candidate decisions are idempotent local records and are also written to the existing Agent OS activity ledger.

## Local model and limitations

The configured model is `qwen3:14b` through the existing local Ollama boundary. The current adapters and deterministic scorer do not require an LLM. Any future summarization remains constrained to local Ollama; there is no hosted or paid fallback.

LIVE research depends on public page availability and stable, legally accessible visible markup, so individual sources can be incomplete or blocked. The MVP has no Amazon login, autonomous schedule, image generation, book production, publishing, advertising, sales ingestion, or long-term autonomous learning.
