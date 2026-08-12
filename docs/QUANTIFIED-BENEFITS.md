# Quantified benefits and reward points

## The problem this solves

`allowance` on a benefit is free-form. Measured across the 61 published
benefits:

- 102 distinct keys
- 45 distinct key-sets, 30 of which occur exactly once

So nearly every benefit has a shape of its own: `discount_percent` beside
`maximum_discount_percent`, `cap_inr` beside `monthly_cap_inr`,
`transaction_cap_inr`, `statement_cycle_cap_inr` and `cap_inr_by_subtype`.
Three different keys spell a foreign-exchange markup. Reward earning appears as
`cashpoints_percent`, `neucoins_per_inr`, `multiplier`,
`partner_tata_non_emi_percent` and `any_upi_percent`, all meaning "what you get
back per rupee", none of them comparable.

Two consequences follow, and both were visible in the product:

1. Nothing can be compared or ranked. "Which of my cards is best for dining"
   is unanswerable without a human reading each entry, which is the question
   the optimizer exists to answer.
2. The interface carries a large map from key names to English, and it grows
   with every new key. When that map lacked an entry the benefit was dropped
   from the screen entirely — nine of sixty vanished that way.

## The shape of the fix

`allowance` stays exactly as it is. It records what the source said, in the
source's own vocabulary, and rewriting it would cost provenance fidelity for
no gain.

A parallel `quantities` list is added: the same facts projected onto a closed
vocabulary so they can be compared. Every entry answers the same questions —
what is earned, per what, capped at what, over what period.

```json
"quantities": [
  {
    "metric": "rate_percent",
    "value": 5,
    "basis": "spend",
    "scope": "amazon.in",
    "period": "statement_cycle",
    "cap": null
  }
]
```

Fields:

| field    | meaning                                                            |
|----------|--------------------------------------------------------------------|
| `metric` | closed vocabulary: what kind of number this is                      |
| `value`  | the number itself                                                   |
| `unit`   | `percent`, `inr`, `points`, `visits`, `tickets`, `multiple`, `days` |
| `basis`  | what the value is per: `spend`, `transaction`, `statement`, `year`  |
| `scope`  | where it applies — a merchant, a channel, or `null` for everywhere  |
| `period` | the window the value or its cap resets over                         |
| `cap`    | `{value, unit, period}` or `null` when uncapped or unknown          |

`metric` is deliberately closed, for the same reason `condition.type` is: an
open vocabulary is how 102 keys happened. Adding a metric is a schema change
that gets reviewed, not a decision made while authoring one benefit.

## Unmapped is recorded, never guessed

Some allowances cannot be projected without inventing meaning —
`partner_and_transfer_terms` is prose, `cap_inr_by_subtype` is a nested map
whose subtypes are not modelled, `not_claimed` is an evidence gap rather than a
quantity.

Those produce **no** `quantities` entry, and the benefit is listed in the
normalization coverage report as unmapped with the reason. A projection that
guessed would be worse than none: it would make a benefit look comparable while
being wrong, and the ranking built on top would be confidently incorrect.

The coverage report is the honest measure of how far this has got, and it is
expected to show unmapped entries indefinitely.

## Reward points are their own model

Reward currencies are not a benefit — they are a per-card earning and
redemption system, and expressing them as isolated benefits is what produced
five incompatible spellings of an earn rate.

`catalog/rewards/<offering-slug>.json` holds one record per card:

```json
{
  "offering_id": "…",
  "currency": "neucoins",
  "base_earn": {"points_per_inr": 0.5},
  "category_earn": [
    {"scope": "grocery", "points_per_inr": 2.5, "cap": {"value": 500, "unit": "points", "period": "month"}}
  ],
  "valuation": {"inr_per_point": 1.0, "basis": "issuer_stated"},
  "expiry": {"months": 12}
}
```

`valuation` is what makes cards comparable: points per rupee is meaningless
across currencies until each is priced in rupees. `basis` records whether that
price is the issuer's own statement or an observation, because those deserve
different confidence and must not silently merge.

Every record carries the same provenance as a benefit — `source_url`,
`content_sha256`, `retrieved_at`, `source_policy_class` — and the same review
state. An unpriced currency is left unpriced rather than estimated.

## Storage

The catalog stays JSON on disk. It is the reviewed, provenance-carrying,
diffable source, and a review that cannot be read as a diff is not a review.

A derived SQLite index is built from it for querying and ranking. It is a
runtime artifact under an ignored local path, never committed, and always
rebuildable from the catalog. Nothing is authored there: if the index and the
JSON disagree, the JSON is right and the index is stale.
