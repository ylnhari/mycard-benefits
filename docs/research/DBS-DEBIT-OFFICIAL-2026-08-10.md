# DBS India debit-card official-source research

Retrieval date: 2026-08-10

Scope: public issuer, administering-party, and network sources only. The
existing generic `dbs-debit` offering is too ambiguous for benefit attachment.
No private card or vault data was accessed. All facts remain `needs_review`.

## Exact public variants

- DBS Visa Signature Debit Card (Aspire): current issuance supported by
  <https://www.dbs.bank.in/digibank/in/banking/account/dbs-aspire>. It states
  Visa Signature, zero FX markup, four domestic lounge visits per year, and an
  Aspire account gate of quarterly TRV INR 1,000,000 or MAB INR 200,000.
- DBS Visa Platinum Debit Card (Growth Max): public account association at
  <https://www.dbs.bank.in/digibank/in/banking/account/savings-power-plus-resident-account>;
  the page advertises Visa Platinum and MAB INR 100,000, but does not prove a
  user-selectable issuance route.
- DBS Treasures Visa Infinite Debit Card: exact family supported by
  <https://www.dbs.bank.in/in/treasures/deposits/your-cards/infinite-debit-card>.
  Do not map it to generic Gold or TPC identifiers because published limits
  conflict.
- DBS EMT Visa Signature Debit Card: exact legacy/paused product at
  <https://www.dbs.bank.in/digibank/in/cards/debit-cards/ease-my-trip>.
  New issuance is explicitly paused.
- Visa Classic, RuPay Classic, RuPay PMJDY, RuPay Platinum, and Visa Business
  appear in the live variant table but lack safe fresh-issuance/account mapping.
- BigBasket Visa Classic remains in the schedule of charges but lacks current
  issuing/product terms; treat as legacy/needs confirmation.

Official variant table:
<https://www.dbs.bank.in/digibank/in/cards/debit-cards/digibank-debit-card>

## Candidate-ready facts

- Lounge terms: <https://www.dbs.bank.in/in/iwov-resources/pdf/debit-card/dbs-bank-lounge-access-tnc.pdf>.
  Infinite two visits per quarter, or four at TRV at least INR 60,000,000;
  Visa Signature one per quarter; EMT Signature one per quarter; Business two
  per quarter; Visa Platinum one per half year; none outside India. From April
  2026, INR 5,000 billed DBS POS/e-commerce spend during the preceding three
  calendar months is required. ATM spend is excluded; a newly issued card is
  exempt for issue month plus three months; validation swipe INR 2; capacity
  and partner availability apply.
- Debit insurance legal matrix:
  <https://www.dbs.bank.in/digibank/in/debit-card-terms-and-conditions.page>.
  Signature/Platinum list unauthorized-use INR 500,000, accident INR 200,000,
  air accident INR 10,000,000, purchase INR 75,000, and checked-baggage
  loss/delay INR 50,000. Infinite lists INR 500,000 / INR 300,000 /
  INR 10,000,000 / INR 100,000 / INR 75,000. One transaction in the preceding
  90 days and primary-cardholder/claim conditions apply. Leave `needs_review`
  because variant/BIN applicability conflicts with presentation pages.
- Aspire wellness is account-programme conditional, not a standalone card
  entitlement: an eligible Aspire relationship plus INR 20,000 cumulative
  debit retail spend in the same quarter; once per financial year; ATM and
  wallet loads excluded. Source:
  <https://www.dbs.bank.in/in/iwov-resources/pdf/aspire-variant-most-important-terms-conditions.pdf>.
- Current fee schedule, effective 13 April 2026:
  <https://www.dbs.bank.in/digibank/in/schedule-of-charges.page>. Fees depend
  on the mapped account; do not attach globally. Aspire is free and later
  reclassification may incur INR 399 plus tax.
- Zero FX may be attached only where current product pages confirm it: Aspire,
  EMT, and Infinite. Do not infer it for every DBS debit offering.
- Visa APAC airport dining: 20 percent at participating locations during 2026,
  subject to country caps and payment with qualifying APAC-issued Visa
  Signature/Infinite. Network source:
  <https://www.visa.co.in/en_in/visa-offers-and-perks/visa-airport-dining/177766>.

## Blocks

- Infinite daily limits conflict between product and generic Gold/TPC tables.
- Do not infer RuPay lounge/insurance without DBS participation or BIN proof.
- No stable DBS points/reward-rate, movie, generic dining, or cashback rule was
  evidenced. Dynamic offers remain discovery-only without exact current terms.
