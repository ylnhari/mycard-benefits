# Roadmap

## Where the product actually is — 2026-08-11

The rebuild replaced the previous build's governance-heavy shape with four
consumer screens. What follows describes the current state, not the former
plan.

1. **Complete: the public catalog.** 72 card products and 60 researched
   benefits drawn from 31 official sources, each retaining its source URL,
   content hash, retrieval date and source classification. Every benefit
   carries one of three states — verified, check before use, or sources
   differ. Where two issuer documents disagree, both claims are kept and
   rendered rather than one being silently chosen. Browsing all of it needs no
   account and no credential.

2. **Complete: the four screens.** My Cards, Benefits, Search and Settings.
   Card faces render at a true 1.586 ratio with a colourway generated from the
   issuer id, so an unknown issuer is distinguishable automatically. Benefits
   group by category with per-category headline selection. Search spans owned
   cards and the catalog, and distinguishes "nobody has researched this" from
   "your cards do not have it".

3. **Complete: the credential model.** The vault opens with a device-held key
   the user never types, so browsing and adding cards ask for nothing. A code
   is created at exactly one moment — the first reveal of a full card number,
   CVV or PIN — and the user chooses a six-digit PIN or a passphrase. The
   Argon2id envelope, its cost parameters, and the escalating delay and lockout
   are unchanged from the original vault.

4. **Complete: the removals.** The candidates, research, agents, sources, qa
   and lifecycle packages are deleted, along with contributor mode and the
   Today view. The research they produced was rescued to `catalog/benefits/`
   and its review metadata to
   `catalog/benefit-review-metadata.json` first.

5. **Not built: coverage.** 18 of 72 products carry researched benefits. The
   other 54 are browsable but have nothing recorded against them, and the app
   says so plainly rather than implying absence. Expanding coverage is the
   largest remaining piece of work and needs source research, not code.

6. **Not built: live source adapters.** Benefits are refreshed by hand. There
   is no scheduled fetching, no change detection against the recorded content
   hashes, and no notification when a source moves. Each of those is separately
   gated on source terms.

7. **Not built: reminders and the purchase-route optimizer UI.** The optimizer
   engine exists and refuses any benefit whose state is not verified, at both
   model construction and the engine boundary. Nothing surfaces it yet, which
   is deliberate: a ranking built on 1 verified benefit would be a control that
   cannot answer.

Each milestone must be independently testable and leave the previous one
usable. Publication is a separate gate and requires the owner's dated approval
naming the exact commit range and destination.

## Release disposition — 2026-08-11

The suite is green: 687 collected, 684 passed, 3 skipped. Accessibility passes
WCAG AA in both themes with no horizontal overflow at 320, 375 or 414 pixels
and no interactive target under 44px. The seven regressions listed in
`docs/design/mycard-design.html` were each checked against the rendered page
and are absent.

`release/public-v1` holds the publishable history as a single commit. The
development history stays local because it carries absolute filesystem paths
from the machine it was built on, and a later cleanup commit would not remove
them from a published history.

Nothing has been pushed.
